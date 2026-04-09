from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from fnmatch import fnmatchcase
from http.cookies import SimpleCookie
from typing import Tuple
from urllib.parse import urlparse

from flask import request

from ..cookies import store_cookie
from ..models import Site
from .constants import (
    ALLOWED_PROXY_PREFIXES,
    ALLOWED_WEBSOCKET_PREFIXES,
    FRAPPE_LOGIN_PATHS,
)


def serialize_site(site: Site) -> dict:
    return {
        "id": site.id,
        "site_id": site.site_id,
        "base_url": site.base_url,
        "user_id": site.user_id,
        "enable_ip_filter": site.enable_ip_filter,
        "ip_filter_mode": site.ip_filter_mode,
        "ip_filters": [f.ip_address for f in site.ip_filters],
        "created_at": site.created_at.isoformat(),
        "updated_at": site.updated_at.isoformat(),
    }


def generate_site_id() -> str:
    latest_site = (
        Site.query.filter(Site.site_id.like("C_____"))
        .order_by(Site.site_id.desc())
        .first()
    )
    if latest_site is None:
        return "C00001"

    try:
        next_value = int(latest_site.site_id[1:]) + 1
    except (TypeError, ValueError):
        next_value = 1

    return f"C{next_value:05d}"


def parse_pagination_params() -> tuple[int, int]:
    try:
        page = int(request.args.get("page", "1"))
    except ValueError:
        page = 1

    try:
        page_size = int(request.args.get("page_size", "20"))
    except ValueError:
        page_size = 20

    page = max(1, page)
    page_size = min(max(1, page_size), 100)
    return page, page_size


def parse_sort_direction() -> str:
    sort_dir = (request.args.get("sort_dir", "desc") or "desc").lower()
    return "asc" if sort_dir == "asc" else "desc"


def is_allowed_proxy_path(path: str) -> bool:
    normalized_path = f"/{path.lstrip('/')}"
    for prefix in ALLOWED_PROXY_PREFIXES:
        if normalized_path == prefix or normalized_path.startswith(f"{prefix}/"):
            return True
    return False


def build_proxy_headers() -> dict:
    excluded_headers = {"host", "content-length", "x-frappe-site"}
    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in excluded_headers
    }
    return headers


def is_frappe_login_path(path: str) -> bool:
    normalized_path = f"/{path.lstrip('/')}"
    return normalized_path in FRAPPE_LOGIN_PATHS


def is_asset_proxy_path(path: str) -> bool:
    normalized_path = f"/{path.lstrip('/')}"
    return normalized_path == "/assets" or normalized_path.startswith("/assets/")


def is_allowed_websocket_path(path: str) -> bool:
    normalized_path = f"/{path.lstrip('/')}"
    for prefix in ALLOWED_WEBSOCKET_PREFIXES:
        if normalized_path == prefix or normalized_path.startswith(f"{prefix}/"):
            return True
    return False


def extract_client_ip() -> str:
    forwarded = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown")
    return forwarded.split(",")[0].strip()


def is_ip_allowed(site: Site, client_ip: str) -> bool:
    if not site.enable_ip_filter:
        return True

    if not client_ip:
        return False

    ip_filter_mode = site.ip_filter_mode or "whitelist"
    ip_filter_exists = any(
        (matches_filter_pattern(client_ip, ip_filter.ip_address) for ip_filter in site.ip_filters)
    )
    if ip_filter_mode == "whitelist":
        return ip_filter_exists
    if ip_filter_mode == "blacklist":
        return not ip_filter_exists
    return False


def matches_filter_pattern(value: str, pattern: str, *, case_sensitive: bool = True) -> bool:
    if not value or not pattern:
        return False

    normalized_value = value.strip()
    normalized_pattern = pattern.strip()
    if not normalized_value or not normalized_pattern:
        return False

    if not case_sensitive:
        normalized_value = normalized_value.lower()
        normalized_pattern = normalized_pattern.lower()

    return fnmatchcase(normalized_value, normalized_pattern)


def parse_cookie_expiration(morsel) -> datetime | None:
    if morsel["max-age"]:
        return datetime.now(UTC) + timedelta(seconds=int(morsel["max-age"]))
    if morsel["expires"]:
        return parsedate_to_datetime(morsel["expires"])
    return None


def store_login_cookie(site: Site, upstream_response) -> Tuple[int, datetime | None]:
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
                "expires_at": parse_cookie_expiration(morsel),
                "path": morsel["path"] or "/",
                "domain": morsel["domain"] or parsed_site_domain,
            },
        )
        return cookie.id, cookie.expires_at if cookie else (0, None)

    return 0, None