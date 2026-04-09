from flask_jwt_extended import create_access_token

from app.health_monitor import run_due_health_checks
from app.models import Log, Site, SiteHealthCheck, User


def create_user(session, username: str) -> User:
    user = User(
        username=username,
        password_hash="hashed-password",
        first_name="Route",
        middle_name=None,
        last_name="User",
        email=f"{username}@example.com",
        email_verified=True,
    )
    session.add(user)
    session.commit()
    return user


def auth_headers(app, user_id: int) -> dict:
    with app.app_context():
        token = create_access_token(identity=str(user_id))
    return {"Authorization": f"Bearer {token}"}


def test_list_sites_returns_only_logged_in_user_sites(app, client, session):
    owner = create_user(session, "siteowner")
    other_user = create_user(session, "othersiteowner")

    session.add(Site(site_id="C00010", base_url="https://owner.example.com", user_id=owner.id))
    session.add(Site(site_id="C00011", base_url="https://other.example.com", user_id=other_user.id))
    session.commit()

    response = client.get("/api/sites", headers=auth_headers(app, owner.id))

    assert response.status_code == 200
    data = response.get_json()
    assert len(data["sites"]) == 1
    assert data["sites"][0]["site_id"] == "C00010"
    assert data["sites"][0]["user_id"] == owner.id


def test_create_site_adds_new_site_for_logged_in_user(app, client, session):
    user = create_user(session, "creator")

    response = client.post(
        "/api/sites",
        headers=auth_headers(app, user.id),
        json={"base_url": "https://create.example.com"},
    )

    assert response.status_code == 201
    data = response.get_json()
    assert data["site"]["site_id"] == "C00001"
    assert data["site"]["base_url"] == "https://create.example.com"
    assert data["site"]["user_id"] == user.id

    saved_site = session.query(Site).filter_by(site_id="C00001").one()
    assert saved_site.user_id == user.id


def test_create_site_runs_health_check_immediately_when_enabled(app, client, session, monkeypatch):
    class MockResponse:
        status_code = 200

    def fake_get(*args, **kwargs):
        return MockResponse()

    app.config["SITE_HEALTH_CHECK_ON_CREATE"] = True
    monkeypatch.setattr("app.health_monitor.requests.get", fake_get)

    user = create_user(session, "createcheck")
    response = client.post(
        "/api/sites",
        headers=auth_headers(app, user.id),
        json={"base_url": "https://created-check.example.com"},
    )

    assert response.status_code == 201
    created_site = response.get_json()["site"]
    health = created_site["health"]
    assert health["checks"] == 1
    assert health["current_status"] == "up"

    saved_site = session.query(Site).filter_by(site_id=created_site["site_id"]).one()
    saved_checks = session.query(SiteHealthCheck).filter_by(site_id=saved_site.id).all()
    assert len(saved_checks) == 1
    assert saved_checks[0].is_up is True


def test_create_site_ignores_client_supplied_site_id(app, client, session):
    user = create_user(session, "generatedsite")

    response = client.post(
        "/api/sites",
        headers=auth_headers(app, user.id),
        json={"site_id": "C99999", "base_url": "https://ignore.example.com"},
    )

    assert response.status_code == 201
    data = response.get_json()
    assert data["site"]["site_id"] == "C00001"
    assert data["site"]["site_id"] != "C99999"


def test_create_site_rejects_malformed_json(app, client, session):
    user = create_user(session, "badjson")

    response = client.post(
        "/api/sites",
        headers=auth_headers(app, user.id),
        data='{"base_url":"https://bad-json.example.com",}',
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "Invalid JSON body"


def test_update_site_edits_logged_in_user_site(app, client, session):
    user = create_user(session, "editor")
    site = Site(site_id="C00013", base_url="https://before.example.com", user_id=user.id)
    session.add(site)
    session.commit()

    response = client.put(
        "/api/sites/C00013",
        headers=auth_headers(app, user.id),
        json={"base_url": "https://after.example.com"},
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["site"]["base_url"] == "https://after.example.com"

    updated_site = session.query(Site).filter_by(site_id="C00013").one()
    assert updated_site.base_url == "https://after.example.com"


def test_update_site_rejects_site_id_changes(app, client, session):
    user = create_user(session, "siteimmutability")
    site = Site(site_id="C00016", base_url="https://stable.example.com", user_id=user.id)
    session.add(site)
    session.commit()

    response = client.put(
        "/api/sites/C00016",
        headers=auth_headers(app, user.id),
        json={"site_id": "C12345", "base_url": "https://changed.example.com"},
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "site_id cannot be modified"

    unchanged_site = session.query(Site).filter_by(site_id="C00016").one()
    assert unchanged_site.base_url == "https://stable.example.com"


def test_delete_site_removes_logged_in_user_site(app, client, session):
    user = create_user(session, "deleterroute")
    site = Site(site_id="C00014", base_url="https://delete.example.com", user_id=user.id)
    session.add(site)
    session.commit()

    response = client.delete(
        "/api/sites/C00014",
        headers=auth_headers(app, user.id),
    )

    assert response.status_code == 200
    assert response.get_json()["message"] == "Site deleted successfully"
    assert session.query(Site).filter_by(site_id="C00014").first() is None


def test_site_routes_store_request_response_logs(app, client, session):
    user = create_user(session, "sitelogger")

    response = client.post(
        "/api/sites",
        headers={
            **auth_headers(app, user.id),
            "X-Test-Header": "site-log-check",
        },
        json={"base_url": "https://log.example.com"},
    )

    assert response.status_code == 201
    created_site = response.get_json()["site"]

    log_entry = session.query(Log).order_by(Log.id.desc()).first()
    assert log_entry is not None
    assert log_entry.method == "POST"
    assert log_entry.path == "/api/sites"
    assert log_entry.response_status == 201
    assert log_entry.site_id == created_site["id"]
    assert log_entry.user_id == user.id
    assert log_entry.headers["X-Test-Header"] == "site-log-check"
    assert log_entry.timestamp is not None


def test_list_sites_includes_health_summary(app, client, session):
    user = create_user(session, "healthlist")
    site = Site(site_id="C00021", base_url="https://health.example.com", user_id=user.id)
    session.add(site)
    session.commit()

    session.add(
        SiteHealthCheck(
            site_id=site.id,
            is_up=True,
            status_code=200,
            response_time_ms=120,
            error_message=None,
        )
    )
    session.commit()

    response = client.get("/api/sites", headers=auth_headers(app, user.id))

    assert response.status_code == 200
    data = response.get_json()
    assert len(data["sites"]) == 1
    health = data["sites"][0]["health"]
    assert health["window_days"] == 90
    assert health["checks"] == 1
    assert health["up_checks"] == 1
    assert health["uptime_percentage"] == 100.0
    assert health["current_status"] == "up"


def test_sites_overview_returns_total_and_status_counts(app, client, session):
    user = create_user(session, "healthoverview")
    up_site = Site(site_id="C00022", base_url="https://up.example.com", user_id=user.id)
    down_site = Site(site_id="C00023", base_url="https://down.example.com", user_id=user.id)
    unknown_site = Site(site_id="C00024", base_url="https://unknown.example.com", user_id=user.id)
    session.add_all([up_site, down_site, unknown_site])
    session.commit()

    session.add_all(
        [
            SiteHealthCheck(site_id=up_site.id, is_up=True, status_code=200, response_time_ms=90),
            SiteHealthCheck(site_id=down_site.id, is_up=False, status_code=503, response_time_ms=250),
        ]
    )
    session.commit()

    response = client.get("/api/sites/overview", headers=auth_headers(app, user.id))

    assert response.status_code == 200
    overview = response.get_json()["overview"]
    assert overview["total_sites"] == 3
    assert overview["up_sites"] == 1
    assert overview["down_sites"] == 1
    assert overview["unknown_sites"] == 1
    assert len(overview["sites"]) == 3


def test_run_due_health_checks_persists_result_for_stale_sites(app, session, monkeypatch):
    class MockResponse:
        status_code = 200

    def fake_get(*args, **kwargs):
        return MockResponse()

    monkeypatch.setattr("app.health_monitor.requests.get", fake_get)

    user = create_user(session, "healthrun")
    site = Site(site_id="C00022", base_url="https://health-run.example.com", user_id=user.id)
    session.add(site)
    session.commit()

    with app.app_context():
        checked_sites = run_due_health_checks()

    assert checked_sites == 1

    saved = session.query(SiteHealthCheck).filter_by(site_id=site.id).all()
    assert len(saved) == 1
    assert saved[0].is_up is True
    assert saved[0].status_code == 200

    with app.app_context():
        checked_sites = run_due_health_checks()

    assert checked_sites == 0
