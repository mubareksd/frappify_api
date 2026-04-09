import os
import sys
from datetime import UTC, datetime, timedelta
from time import perf_counter
from threading import Event, Lock, Thread
from urllib.parse import urlparse

import requests
from flask import current_app

from .extensions import db
from .models import Site, SiteHealthCheck


_monitor_thread: Thread | None = None
_monitor_stop_event: Event | None = None
_monitor_lock = Lock()


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


def _freshness_cutoff() -> datetime:
    freshness_seconds = int(
        current_app.config.get("SITE_HEALTH_CHECK_FRESHNESS_SECONDS", 300)
    )
    return _utc_now() - timedelta(seconds=freshness_seconds)


def site_requires_health_check(site: Site) -> bool:
    latest = latest_health_check(site.id)
    if latest is None:
        return True

    checked_at = _normalize_checked_at(latest.checked_at)
    if checked_at is None:
        return True

    return checked_at < _freshness_cutoff()


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


def run_due_health_checks(*, limit: int | None = None) -> int:
    checked_sites = 0
    sites = Site.query.order_by(Site.id.asc()).all()

    for site in sites:
        if not site_requires_health_check(site):
            continue

        try:
            run_site_health_check(site)
            checked_sites += 1
        except Exception:
            db.session.rollback()
            current_app.logger.exception(
                "Site health check failed", extra={"site_id": site.site_id}
            )

        if limit is not None and checked_sites >= limit:
            break

    return checked_sites


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


def sites_health_overview(*, user_id: int | None = None, days: int = 90) -> dict:
    query = Site.query.order_by(Site.id.asc())
    if user_id is not None:
        query = query.filter_by(user_id=user_id)

    sites = query.all()
    site_summaries = []
    up_sites = 0
    down_sites = 0
    unknown_sites = 0
    checked_sites = 0
    uptime_totals = []

    for site in sites:
        summary = health_summary(site.id, days=days)
        status = summary["current_status"]
        if status == "up":
            up_sites += 1
        elif status == "down":
            down_sites += 1
        else:
            unknown_sites += 1

        if summary["checks"] > 0:
            checked_sites += 1
        if summary["uptime_percentage"] is not None:
            uptime_totals.append(summary["uptime_percentage"])

        site_summaries.append(
            {
                "id": site.id,
                "site_id": site.site_id,
                "base_url": site.base_url,
                "current_status": status,
                "uptime_percentage": summary["uptime_percentage"],
                "checks": summary["checks"],
                "last_checked_at": summary["last_checked_at"],
            }
        )

    average_uptime_percentage = None
    if uptime_totals:
        average_uptime_percentage = round(sum(uptime_totals) / len(uptime_totals), 2)

    return {
        "window_days": days,
        "total_sites": len(sites),
        "up_sites": up_sites,
        "down_sites": down_sites,
        "unknown_sites": unknown_sites,
        "checked_sites": checked_sites,
        "average_uptime_percentage": average_uptime_percentage,
        "sites": site_summaries,
    }


def _should_start_monitor(app) -> bool:
    if app.testing:
        return False
    if not app.config.get("SITE_HEALTH_MONITORING_ENABLED", True):
        return False
    if len(sys.argv) > 1 and sys.argv[1] == "db":
        return False
    if app.debug and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        return False
    return True


def _monitor_loop(app, stop_event: Event) -> None:
    interval_seconds = int(
        app.config.get("SITE_HEALTH_MONITOR_INTERVAL_SECONDS", 300)
    )
    batch_size = app.config.get("SITE_HEALTH_MONITOR_BATCH_SIZE")

    while not stop_event.is_set():
        with app.app_context():
            run_due_health_checks(limit=batch_size)

        if stop_event.wait(interval_seconds):
            break


def start_health_monitor(app) -> None:
    global _monitor_thread, _monitor_stop_event

    if not _should_start_monitor(app):
        return

    with _monitor_lock:
        if _monitor_thread is not None and _monitor_thread.is_alive():
            return

        _monitor_stop_event = Event()
        _monitor_thread = Thread(
            target=_monitor_loop,
            args=(app, _monitor_stop_event),
            daemon=True,
            name="site-health-monitor",
        )
        _monitor_thread.start()