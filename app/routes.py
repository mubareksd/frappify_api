from http import HTTPStatus
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from http.cookies import SimpleCookie
from typing import Tuple
from urllib.parse import urlparse

import requests
from flask import Blueprint, Response, g, jsonify, request
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    get_jwt_identity,
    jwt_required,
    verify_jwt_in_request,
)

from .auth import (
    generate_email_verification_token,
    generate_password_reset_token,
    send_password_reset_email,
    send_verification_email,
    verify_email_token,
    verify_password_reset_token,
)
from .cookies import get_valid_cookie_by_id, store_cookie
from .extensions import db
from .models import Cookie, Log, Site, User


api_bp = Blueprint("api", __name__)
ALLOWED_PROXY_PREFIXES = (
    "/method",
    "/resource",
    "/assets",
    "/v1/method",
    "/v1/resource",
    "/v2/method",
    "/v2/document",
    "/v2/doctype",
)
PROXY_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]
FRAPPE_LOGIN_PATHS = {
    "/method/login",
    "/v1/method/login",
    "/v2/method/login",
}


def _serialize_site(site: Site) -> dict:
    return {
        "id": site.id,
        "site_id": site.site_id,
        "base_url": site.base_url,
        "user_id": site.user_id,
        "created_at": site.created_at.isoformat(),
        "updated_at": site.updated_at.isoformat(),
    }


def _is_allowed_proxy_path(path: str) -> bool:
    normalized_path = f"/{path.lstrip('/')}"
    for prefix in ALLOWED_PROXY_PREFIXES:
        if normalized_path == prefix or normalized_path.startswith(f"{prefix}/"):
            return True
    return False


def _build_proxy_headers() -> dict:
    excluded_headers = {"host", "content-length", "x-frappe-site"}
    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in excluded_headers
    }
    return headers


def _is_frappe_login_path(path: str) -> bool:
    normalized_path = f"/{path.lstrip('/')}"
    return normalized_path in FRAPPE_LOGIN_PATHS


def _is_asset_proxy_path(path: str) -> bool:
    normalized_path = f"/{path.lstrip('/')}"
    return normalized_path == "/assets" or normalized_path.startswith("/assets/")


def _parse_cookie_expiration(morsel) -> datetime | None:
    if morsel["max-age"]:
        return datetime.now(UTC) + timedelta(seconds=int(morsel["max-age"]))
    if morsel["expires"]:
        return parsedate_to_datetime(morsel["expires"])
    return None


def _store_login_cookie(site: Site, upstream_response) -> Tuple[int, datetime | None]:
    set_cookie_header = upstream_response.headers.get("Set-Cookie")
    if not set_cookie_header:
        return 0, None

    parsed_cookie = SimpleCookie()
    parsed_cookie.load(set_cookie_header)
    parsed_site_domain = urlparse(site.base_url).hostname or ""

    for morsel in parsed_cookie.values():
        cookie = store_cookie(
            site.id,
            {
                "cookie_name": morsel.key,
                "cookie_value": morsel.value,
                "expires_at": _parse_cookie_expiration(morsel),
                "path": morsel["path"] or "/",
                "domain": morsel["domain"] or parsed_site_domain,
            },
        )
        return cookie.id, cookie.expires_at if cookie else (0, None)


@api_bp.get("/hello")
def hello_world():
    return jsonify({"message": "Hello World from Flask"})


@api_bp.get("/health")
def health():
    return jsonify({"status": "ok"})


@api_bp.get("/dashboard/summary")
def dashboard_summary():
    return jsonify(
        {
            "counts": {
                "users": User.query.count(),
                "sites": Site.query.count(),
                "cookies": Cookie.query.count(),
                "logs": Log.query.count(),
            }
        }
    )


@api_bp.post("/auth/register")
def register():
    payload = request.get_json(silent=True) or {}
    required_fields = [
        "username",
        "password",
        "first_name",
        "last_name",
        "email",
    ]
    missing_fields = [field for field in required_fields if not payload.get(field)]

    if missing_fields:
        return (
            jsonify({"error": f"Missing required fields: {', '.join(missing_fields)}"}),
            HTTPStatus.BAD_REQUEST,
        )

    existing_user = User.query.filter(
        (User.username == payload["username"]) | (User.email == payload["email"])
    ).first()
    if existing_user:
        return (
            jsonify({"error": "A user with that username or email already exists"}),
            HTTPStatus.CONFLICT,
        )

    user = User(
        username=payload["username"],
        first_name=payload["first_name"],
        middle_name=payload.get("middle_name"),
        last_name=payload["last_name"],
        email=payload["email"],
        email_verified=False,
    )
    user.set_password(payload["password"])

    db.session.add(user)
    db.session.commit()

    # token = generate_email_verification_token(user.id)
    # send_verification_email(user.email, token)

    return (
        jsonify(
            {
                "message": "Registration successful. Please verify your email.",
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "email_verified": user.email_verified,
                },
            }
        ),
        HTTPStatus.CREATED,
    )


@api_bp.get("/auth/verify-email")
def verify_email():
    token = request.args.get("token")
    if not token:
        return jsonify({"error": "Verification token is required"}), HTTPStatus.BAD_REQUEST

    user_id = verify_email_token(token)
    if user_id is None:
        return jsonify({"error": "Invalid or expired verification token"}), HTTPStatus.BAD_REQUEST

    user = db.session.get(User, user_id)
    if user is None:
        return jsonify({"error": "User not found"}), HTTPStatus.NOT_FOUND

    user.email_verified = True
    db.session.commit()

    return jsonify({"message": "Email verified successfully"}), HTTPStatus.OK


@api_bp.post("/auth/login")
def login():
    payload = request.get_json(silent=True) or {}
    username = payload.get("username")
    password = payload.get("password")

    if not username or not password:
        return (
            jsonify({"error": "Username and password are required"}),
            HTTPStatus.BAD_REQUEST,
        )

    user = User.query.filter_by(username=username).first()
    if user is None or not user.check_password(password):
        return jsonify({"error": "Invalid credentials"}), HTTPStatus.UNAUTHORIZED

    access_token = create_access_token(identity=str(user.id))
    refresh_token = create_refresh_token(identity=str(user.id))

    return (
        jsonify(
            {
                "access_token": access_token,
                "access_token_expires_in": 15 * 60,  # 15 minutes
                "refresh_token": refresh_token,
                "refresh_token_expires_in": 7 * 24 * 60 * 60,  # 7 days
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "email_verified": user.email_verified,
                },
            }
        ),
        HTTPStatus.OK,
    )


@api_bp.post("/auth/refresh")
@jwt_required(refresh=True)
def refresh():
    access_token = create_access_token(identity=get_jwt_identity())
    return jsonify({"access_token": access_token, "access_token_expires_in": 15 * 60}), HTTPStatus.OK


@api_bp.post("/auth/forgot-password")
def forgot_password():
    payload = request.get_json(silent=True) or {}
    email = payload.get("email")

    if not email:
        return jsonify({"error": "Email is required"}), HTTPStatus.BAD_REQUEST

    user = User.query.filter_by(email=email).first()
    if user is not None:
        token = generate_password_reset_token(user.id)
        send_password_reset_email(user.email, token)

    return (
        jsonify(
            {
                "message": (
                    "If an account with that email exists, a password reset email has been sent."
                )
            }
        ),
        HTTPStatus.OK,
    )


@api_bp.post("/auth/reset-password")
def reset_password():
    payload = request.get_json(silent=True) or {}
    token = payload.get("token")
    new_password = payload.get("password")

    if not token or not new_password:
        return (
            jsonify({"error": "Token and password are required"}),
            HTTPStatus.BAD_REQUEST,
        )

    user_id = verify_password_reset_token(token)
    if user_id is None:
        return jsonify({"error": "Invalid or expired reset token"}), HTTPStatus.BAD_REQUEST

    user = db.session.get(User, user_id)
    if user is None:
        return jsonify({"error": "User not found"}), HTTPStatus.NOT_FOUND

    user.set_password(new_password)
    db.session.commit()

    return jsonify({"message": "Password reset successfully"}), HTTPStatus.OK


@api_bp.get("/sites")
@jwt_required()
def list_sites():
    user_id = int(get_jwt_identity())
    sites = Site.query.filter_by(user_id=user_id).order_by(Site.id.asc()).all()
    return jsonify({"sites": [_serialize_site(site) for site in sites]}), HTTPStatus.OK


@api_bp.post("/sites")
@jwt_required()
def create_site():
    user_id = int(get_jwt_identity())
    payload = request.get_json(silent=True) or {}
    site_id = payload.get("site_id")
    base_url = payload.get("base_url")

    if not site_id or not base_url:
        return (
            jsonify({"error": "site_id and base_url are required"}),
            HTTPStatus.BAD_REQUEST,
        )

    existing_site = Site.query.filter_by(site_id=site_id).first()
    if existing_site is not None:
        return jsonify({"error": "A site with that site_id already exists"}), HTTPStatus.CONFLICT

    site = Site(site_id=site_id, base_url=base_url, user_id=user_id)
    db.session.add(site)
    db.session.commit()
    g.log_site_id = site.site_id

    return jsonify({"site": _serialize_site(site)}), HTTPStatus.CREATED


@api_bp.put("/sites/<string:site_id>")
@jwt_required()
def update_site(site_id: str):
    user_id = int(get_jwt_identity())
    site = Site.query.filter_by(site_id=site_id, user_id=user_id).first()
    if site is None:
        return jsonify({"error": "Site not found"}), HTTPStatus.NOT_FOUND
    g.log_site_id = site.site_id

    payload = request.get_json(silent=True) or {}
    next_site_id = payload.get("site_id", site.site_id)
    next_base_url = payload.get("base_url", site.base_url)

    if not next_site_id or not next_base_url:
        return (
            jsonify({"error": "site_id and base_url are required"}),
            HTTPStatus.BAD_REQUEST,
        )

    duplicate_site = Site.query.filter(
        Site.site_id == next_site_id,
        Site.id != site.id,
    ).first()
    if duplicate_site is not None:
        return jsonify({"error": "A site with that site_id already exists"}), HTTPStatus.CONFLICT

    site.site_id = next_site_id
    site.base_url = next_base_url
    db.session.commit()
    g.log_site_id = site.site_id

    return jsonify({"site": _serialize_site(site)}), HTTPStatus.OK


@api_bp.delete("/sites/<string:site_id>")
@jwt_required()
def delete_site(site_id: str):
    user_id = int(get_jwt_identity())
    site = Site.query.filter_by(site_id=site_id, user_id=user_id).first()
    if site is None:
        return jsonify({"error": "Site not found"}), HTTPStatus.NOT_FOUND
    g.log_site_id = site.site_id

    db.session.delete(site)
    db.session.commit()

    return jsonify({"message": "Site deleted successfully"}), HTTPStatus.OK


@api_bp.route("/<path:path>", methods=PROXY_METHODS)
@api_bp.route("/", defaults={"path": ""}, methods=PROXY_METHODS)
def proxy_request(path: str):
    if not _is_allowed_proxy_path(path):
        return jsonify({"error": "Proxy path is not allowed"}), HTTPStatus.BAD_REQUEST

    target_site_id = request.headers.get("X-Frappe-Site")
    if not target_site_id:
        return jsonify({"error": "X-Frappe-Site header is required"}), HTTPStatus.BAD_REQUEST

    site = Site.query.filter_by(site_id=target_site_id).first()
    if site is None:
        return jsonify({"error": "Site not found"}), HTTPStatus.NOT_FOUND
    g.log_site_id = site.site_id

    proxied_path = path.lstrip("/")
    if _is_asset_proxy_path(path):
        upstream_url = f"{site.base_url.rstrip('/')}/{proxied_path}"
    else:
        upstream_url = f"{site.base_url.rstrip('/')}/api/{proxied_path}"
    if request.query_string:
        upstream_url = f"{upstream_url}?{request.query_string.decode()}"

    headers = _build_proxy_headers()
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

    if _is_frappe_login_path(path):
        cookie_id, expires_at = _store_login_cookie(site, upstream_response)
        if (cookie_id == 0):
            return jsonify({"error": "Failed to store login cookie"}), HTTPStatus.INTERNAL_SERVER_ERROR
        
        # match expires_at to the cookie expiration if available, otherwise default to 7 days
        expires_delta = timedelta(days=7)
        if expires_at:
            expires_delta = expires_at - datetime.utcnow()
        access_token = create_access_token(identity=str(cookie_id), expires_delta=expires_delta)
        return jsonify({
            "access_token": access_token, "expires_in": expires_delta.total_seconds()
                })

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
