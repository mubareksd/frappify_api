from datetime import UTC, datetime, timedelta
from http import HTTPStatus

import requests
from flask import Response, g, jsonify, request
from flask_jwt_extended import create_access_token, get_jwt_identity, verify_jwt_in_request
from sqlalchemy.exc import OperationalError

from ..cookies import get_valid_cookie_by_id
from ..extensions import db
from ..models import Site
from . import api_bp
from .constants import PROXY_METHODS
from .utils import (
    build_proxy_headers,
    extract_client_ip,
    is_allowed_proxy_path,
    is_asset_proxy_path,
    is_frappe_login_path,
    is_ip_allowed,
    store_login_cookie,
)


@api_bp.route("/<path:path>", methods=PROXY_METHODS)
@api_bp.route("/", defaults={"path": ""}, methods=PROXY_METHODS)
def proxy_request(path: str):
    if not is_allowed_proxy_path(path):
        return jsonify({"error": "Proxy path is not allowed"}), HTTPStatus.BAD_REQUEST

    target_site_id = request.headers.get("X-Frappe-Site")
    if not target_site_id:
        return jsonify({"error": "X-Frappe-Site header is required"}), HTTPStatus.BAD_REQUEST

    site = None
    for attempt in range(2):
        try:
            site = Site.query.filter_by(site_id=target_site_id).first()
            break
        except OperationalError:
            db.session.rollback()
            if attempt == 1:
                return (
                    jsonify({"error": "Database unavailable. Please try again."}),
                    HTTPStatus.SERVICE_UNAVAILABLE,
                )

    if site is None:
        return jsonify({"error": "Site not found"}), HTTPStatus.NOT_FOUND
    g.log_site_id = site.id

    client_ip = extract_client_ip()
    if site.enable_ip_filter and not client_ip:
        return jsonify({"error": "Unable to determine client IP address"}), HTTPStatus.BAD_REQUEST
    if not is_ip_allowed(site, client_ip):
        return jsonify({"error": "Access denied due to IP filter rules"}), HTTPStatus.FORBIDDEN

    proxied_path = path.lstrip("/")
    if is_asset_proxy_path(path):
        upstream_url = f"{site.base_url.rstrip('/')}/{proxied_path}"
    else:
        upstream_url = f"{site.base_url.rstrip('/')}/api/{proxied_path}"
    if request.query_string:
        upstream_url = f"{upstream_url}?{request.query_string.decode()}"

    headers = build_proxy_headers()
    authorization_header = request.headers.get("Authorization")
    if authorization_header and authorization_header.startswith("Bearer "):
        try:
            verify_jwt_in_request()
            identity = get_jwt_identity()
            if identity is None:
                return jsonify({"error": "Invalid JWT token"}), HTTPStatus.UNAUTHORIZED
            cookie = get_valid_cookie_by_id(site.id, int(identity))
            if cookie is None:
                return jsonify({"error": "No valid cookie found for the provided JWT token"}), HTTPStatus.UNAUTHORIZED
            headers["Cookie"] = f"{cookie.cookie_name}={cookie.cookie_value}"
        except Exception as e:
            return jsonify({"error": f"JWT token error: {str(e)}"}), HTTPStatus.UNAUTHORIZED

    upstream_response = requests.request(
        method=request.method,
        url=upstream_url,
        headers=headers,
        data=request.get_data(),
        allow_redirects=False,
    )

    if is_frappe_login_path(path):
        cookie_id, expires_at = store_login_cookie(site, upstream_response)
        if cookie_id == 0:
            return jsonify({"error": "Failed to store login cookie"}), HTTPStatus.INTERNAL_SERVER_ERROR

        expires_delta = timedelta(days=7)
        if expires_at:
            normalized_expires_at = expires_at
            if normalized_expires_at.tzinfo is None:
                normalized_expires_at = normalized_expires_at.replace(tzinfo=UTC)
            expires_delta = max(
                normalized_expires_at - datetime.now(UTC), timedelta(seconds=0)
            )
        access_token = create_access_token(identity=str(cookie_id), expires_delta=expires_delta)
        return jsonify({"access_token": access_token, "expires_in": expires_delta.total_seconds()})

    response_headers = {
        key: value
        for key, value in upstream_response.headers.items()
        if key.lower() not in {"content-length", "transfer-encoding", "connection"}
    }

    return Response(
        upstream_response.content,
        status=upstream_response.status_code,
        headers=response_headers,
    )