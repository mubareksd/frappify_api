from datetime import UTC, datetime, timedelta
from time import perf_counter
from urllib.parse import urlparse

import requests
from flask import current_app

from .extensions import db
from .models import Site, SiteHealthCheck


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _normalize_checked_at(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _target_url(site: Site) -> str:
    parsed = urlparse(site.base_url)
    if not parsed.scheme or not parsed.netloc:
        return site.base_url
    return f"{parsed.scheme}://{parsed.netloc}"


def is_monitoring_enabled() -> bool:
    return bool(current_app.config.get("SITE_HEALTH_MONITORING_ENABLED", True))


def run_site_health_check(site: Site) -> SiteHealthCheck:
    timeout = int(current_app.config.get("SITE_HEALTH_CHECK_TIMEOUT_SECONDS", 8))
    target_url = _target_url(site)
    started = perf_counter()

    is_up = False
    status_code = None
    response_time_ms = None
    error_message = None

    try:
        response = requests.get(target_url, timeout=timeout, allow_redirects=True)
        elapsed_ms = int((perf_counter() - started) * 1000)
        status_code = response.status_code
        response_time_ms = elapsed_ms
        is_up = 200 <= response.status_code < 400
    except requests.RequestException as exc:
        error_message = str(exc)

    health_check = SiteHealthCheck(
        site_id=site.id,
        is_up=is_up,
        status_code=status_code,
        response_time_ms=response_time_ms,
        error_message=error_message,
        checked_at=_utc_now(),
    )
    db.session.add(health_check)
    db.session.commit()

    _prune_old_checks(site.id)
    return health_check


def _prune_old_checks(site_id: int) -> None:
    retention_days = int(current_app.config.get("SITE_HEALTH_RETENTION_DAYS", 120))
    cutoff = _utc_now() - timedelta(days=retention_days)
    SiteHealthCheck.query.filter(
        SiteHealthCheck.site_id == site_id,
        SiteHealthCheck.checked_at < cutoff,
    ).delete(synchronize_session=False)
    db.session.commit()


def ensure_recent_health_check(site: Site) -> SiteHealthCheck | None:
    if not is_monitoring_enabled():
        return latest_health_check(site.id)

    freshness_seconds = int(current_app.config.get("SITE_HEALTH_CHECK_FRESHNESS_SECONDS", 300))
    latest = latest_health_check(site.id)
    if latest is None:
        return run_site_health_check(site)

    checked_at = _normalize_checked_at(latest.checked_at)
    if checked_at is None:
        return run_site_health_check(site)

    if checked_at >= _utc_now() - timedelta(seconds=freshness_seconds):
        return latest

    return run_site_health_check(site)


def latest_health_check(site_id: int) -> SiteHealthCheck | None:
    return (
        SiteHealthCheck.query.filter_by(site_id=site_id)
        .order_by(SiteHealthCheck.checked_at.desc(), SiteHealthCheck.id.desc())
        .first()
    )


def health_summary(site_id: int, *, days: int = 90) -> dict:
    latest = latest_health_check(site_id)
    cutoff = _utc_now() - timedelta(days=days)

    checks = SiteHealthCheck.query.filter(
        SiteHealthCheck.site_id == site_id,
        SiteHealthCheck.checked_at >= cutoff,
    )
    total = checks.count()
    up_total = checks.filter(SiteHealthCheck.is_up.is_(True)).count()

    uptime_percentage = None
    if total > 0:
        uptime_percentage = round((up_total / total) * 100, 2)

    current_status = "unknown"
    if latest is not None:
        current_status = "up" if latest.is_up else "down"

    return {
        "window_days": days,
        "checks": total,
        "up_checks": up_total,
        "uptime_percentage": uptime_percentage,
        "current_status": current_status,
        "last_checked_at": latest.checked_at.isoformat() if latest else None,
        "last_status_code": latest.status_code if latest else None,
        "last_response_time_ms": latest.response_time_ms if latest else None,
        "last_error": latest.error_message if latest else None,
    }