from http import HTTPStatus

from flask import g, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..models import IpFilter, Log, Site
from . import api_bp
from .utils import (
    generate_site_id,
    parse_pagination_params,
    parse_sort_direction,
    serialize_site,
)


@api_bp.get("/sites/<string:site_id>/logs")
@jwt_required()
def list_site_logs(site_id: str):
    user_id = int(get_jwt_identity())
    site = Site.query.filter_by(site_id=site_id, user_id=user_id).first()
    if site is None:
        return jsonify({"error": "Site not found"}), HTTPStatus.NOT_FOUND

    page, page_size = parse_pagination_params()
    offset = (page - 1) * page_size

    search = (request.args.get("search", "") or "").strip()
    method = (request.args.get("method", "") or "").strip().upper()
    status = (request.args.get("status", "") or "").strip()
    sort_by = (request.args.get("sort_by", "timestamp") or "timestamp").strip().lower()
    sort_dir = parse_sort_direction()

    allowed_sort_columns = {
        "timestamp": Log.timestamp,
        "method": Log.method,
        "path": Log.path,
        "ip_address": Log.ip_address,
        "response_status": Log.response_status,
    }
    sort_column = allowed_sort_columns.get(sort_by, Log.timestamp)
    if sort_by not in allowed_sort_columns:
        sort_by = "timestamp"

    query = Log.query.filter_by(site_id=site.id)

    if search:
        like_pattern = f"%{search}%"
        query = query.filter(
            (Log.path.ilike(like_pattern))
            | (Log.ip_address.ilike(like_pattern))
            | (Log.method.ilike(like_pattern))
        )

    if method:
        query = query.filter(Log.method == method)

    if status:
        try:
            query = query.filter(Log.response_status == int(status))
        except ValueError:
            return jsonify({"error": "status must be a valid integer"}), HTTPStatus.BAD_REQUEST

    total = query.count()
    total_pages = max(1, (total + page_size - 1) // page_size)

    if sort_dir == "asc":
        query = query.order_by(sort_column.asc(), Log.id.asc())
    else:
        query = query.order_by(sort_column.desc(), Log.id.desc())

    logs = query.offset(offset).limit(page_size).all()

    def serialize_log(log):
        return {
            "id": log.id,
            "timestamp": log.timestamp.isoformat() if log.timestamp else None,
            "method": log.method,
            "path": log.path,
            "headers": log.headers,
            "ip_address": log.ip_address,
            "response_status": log.response_status,
            "user_id": log.user_id,
        }

    return (
        jsonify(
            {
                "logs": [serialize_log(log) for log in logs],
                "meta": {
                    "page": page,
                    "page_size": page_size,
                    "total": total,
                    "total_pages": total_pages,
                    "sort_by": sort_by,
                    "sort_dir": sort_dir,
                    "search": search,
                    "method": method,
                    "status": status,
                },
            }
        ),
        HTTPStatus.OK,
    )


@api_bp.get("/sites")
@jwt_required()
def list_sites():
    user_id = int(get_jwt_identity())
    page, page_size = parse_pagination_params()
    offset = (page - 1) * page_size

    search = (request.args.get("search", "") or "").strip()
    enable_ip_filter = (request.args.get("enable_ip_filter", "") or "").strip().lower()
    sort_by = (request.args.get("sort_by", "id") or "id").strip().lower()
    sort_dir = parse_sort_direction()

    allowed_sort_columns = {
        "id": Site.id,
        "site_id": Site.site_id,
        "base_url": Site.base_url,
        "created_at": Site.created_at,
        "updated_at": Site.updated_at,
    }
    sort_column = allowed_sort_columns.get(sort_by, Site.id)
    if sort_by not in allowed_sort_columns:
        sort_by = "id"

    query = Site.query.filter_by(user_id=user_id)

    if search:
        like_pattern = f"%{search}%"
        query = query.filter(
            (Site.site_id.ilike(like_pattern)) | (Site.base_url.ilike(like_pattern))
        )

    if enable_ip_filter in {"true", "false"}:
        query = query.filter(Site.enable_ip_filter == (enable_ip_filter == "true"))

    total = query.count()
    total_pages = max(1, (total + page_size - 1) // page_size)

    if sort_dir == "asc":
        query = query.order_by(sort_column.asc(), Site.id.asc())
    else:
        query = query.order_by(sort_column.desc(), Site.id.desc())

    sites = query.offset(offset).limit(page_size).all()
    return (
        jsonify(
            {
                "sites": [serialize_site(site) for site in sites],
                "meta": {
                    "page": page,
                    "page_size": page_size,
                    "total": total,
                    "total_pages": total_pages,
                    "sort_by": sort_by,
                    "sort_dir": sort_dir,
                    "search": search,
                    "enable_ip_filter": enable_ip_filter,
                },
            }
        ),
        HTTPStatus.OK,
    )


@api_bp.post("/sites")
@jwt_required()
def create_site():
    user_id = int(get_jwt_identity())
    payload = request.get_json(silent=False)
    if payload is None:
        return jsonify({"error": "Invalid JSON body"}), HTTPStatus.BAD_REQUEST
    if not isinstance(payload, dict):
        return jsonify({"error": "JSON body must be an object"}), HTTPStatus.BAD_REQUEST

    base_url = payload.get("base_url")
    enable_ip_filter = payload.get("enable_ip_filter", False)
    ip_filter_mode = payload.get("ip_filter_mode", "whitelist")
    ip_filters = payload.get("ip_filters", [])

    if not base_url:
        return jsonify({"error": "base_url is required"}), HTTPStatus.BAD_REQUEST

    site = None
    for _ in range(5):
        site = Site(
            site_id=generate_site_id(),
            base_url=base_url,
            user_id=user_id,
            enable_ip_filter=enable_ip_filter,
            ip_filter_mode=ip_filter_mode,
        )
        db.session.add(site)
        try:
            db.session.commit()
            break
        except IntegrityError:
            db.session.rollback()
            site = None

    if site is None:
        return jsonify({"error": "Unable to generate a unique site_id"}), HTTPStatus.INTERNAL_SERVER_ERROR

    if enable_ip_filter:
        for ip in ip_filters:
            site.ip_filters.append(IpFilter(ip_address=ip))

    db.session.commit()
    g.log_site_id = site.id

    return jsonify({"site": serialize_site(site)}), HTTPStatus.CREATED


@api_bp.put("/sites/<string:site_id>")
@jwt_required()
def update_site(site_id: str):
    user_id = int(get_jwt_identity())
    site = Site.query.filter_by(site_id=site_id, user_id=user_id).first()
    if site is None:
        return jsonify({"error": "Site not found"}), HTTPStatus.NOT_FOUND
    g.log_site_id = site.id

    payload = request.get_json(silent=True) or {}
    next_base_url = payload.get("base_url", site.base_url)

    if payload.get("site_id") not in (None, site.site_id):
        return jsonify({"error": "site_id cannot be modified"}), HTTPStatus.BAD_REQUEST

    if not next_base_url:
        return jsonify({"error": "base_url is required"}), HTTPStatus.BAD_REQUEST

    site.base_url = next_base_url

    if "enable_ip_filter" in payload:
        site.enable_ip_filter = bool(payload["enable_ip_filter"])
    if "ip_filter_mode" in payload:
        site.ip_filter_mode = payload["ip_filter_mode"]
    if "ip_filters" in payload:
        site.ip_filters.clear()
        for ip in payload["ip_filters"]:
            site.ip_filters.append(IpFilter(ip_address=ip))

    db.session.commit()
    g.log_site_id = site.id

    return jsonify({"site": serialize_site(site)}), HTTPStatus.OK


@api_bp.delete("/sites/<string:site_id>")
@jwt_required()
def delete_site(site_id: str):
    user_id = int(get_jwt_identity())
    site = Site.query.filter_by(site_id=site_id, user_id=user_id).first()
    if site is None:
        return jsonify({"error": "Site not found"}), HTTPStatus.NOT_FOUND
    g.log_site_id = site.id

    db.session.delete(site)
    db.session.commit()

    return jsonify({"message": "Site deleted successfully"}), HTTPStatus.OK