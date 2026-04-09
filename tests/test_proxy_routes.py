from datetime import UTC, datetime, timedelta

from flask_jwt_extended import create_access_token

from app.cookies import get_valid_cookie, store_cookie
from app.models import Cookie, Log, Site, User


def create_user(session, username: str = "proxyowner") -> User:
    user = User(
        username=username,
        password_hash="hashed-password",
        first_name="Proxy",
        middle_name=None,
        last_name="Owner",
        email=f"{username}@example.com",
        email_verified=True,
    )
    session.add(user)
    session.commit()
    return user


def create_site(session, user: User, site_code: str = "C00300") -> Site:
    site = Site(site_id=site_code, base_url="https://frappe.example.com", user_id=user.id)
    session.add(site)
    session.commit()
    return site


class MockUpstreamResponse:
    def __init__(self, content: bytes, status_code: int, headers: dict):
        self.content = content
        self.status_code = status_code
        self.headers = headers


def test_proxy_forwards_request_to_frappe_site(client, session, monkeypatch):
    user = create_user(session)
    site = create_site(session, user)
    captured_request = {}

    def fake_request(method, url, headers, data, allow_redirects):
        captured_request["method"] = method
        captured_request["url"] = url
        captured_request["headers"] = headers
        captured_request["data"] = data
        captured_request["allow_redirects"] = allow_redirects
        return MockUpstreamResponse(
            b'{"ok": true}',
            202,
            {"Content-Type": "application/json", "X-Upstream": "frappe"},
        )

    monkeypatch.setattr("app.routes.proxy.requests.request", fake_request)

    response = client.post(
        "/api/resource/ToDo?limit=5",
        headers={
            "X-Frappe-Site": site.site_id,
            "Content-Type": "application/json",
            "X-Test-Header": "proxy-check",
        },
        data=b'{"name":"Test"}',
    )

    assert response.status_code == 202
    assert response.data == b'{"ok": true}'
    assert response.headers["Content-Type"] == "application/json"
    assert response.headers["X-Upstream"] == "frappe"
    assert captured_request["method"] == "POST"
    assert captured_request["url"] == "https://frappe.example.com/api/resource/ToDo?limit=5"
    assert captured_request["headers"]["X-Test-Header"] == "proxy-check"
    assert captured_request["data"] == b'{"name":"Test"}'
    assert captured_request["allow_redirects"] is False


def test_proxy_attaches_cookie_for_valid_proxy_token(client, session, monkeypatch):
    user = create_user(session, username="proxycookieuser")
    site = create_site(session, user, site_code="C00301")
    stored_cookie = store_cookie(
        site.id,
        {
            "cookie_name": "sid",
            "cookie_value": "cookie-123",
            "expires_at": datetime.now(UTC) + timedelta(minutes=30),
            "path": "/",
            "domain": "frappe.example.com",
        },
    )

    with client.application.app_context():
        access_token = create_access_token(identity=str(stored_cookie.id))

    captured_request = {}

    def fake_request(method, url, headers, data, allow_redirects):
        captured_request["headers"] = headers
        return MockUpstreamResponse(b"cookie attached", 200, {"Content-Type": "text/plain"})

    monkeypatch.setattr("app.routes.proxy.requests.request", fake_request)

    response = client.get(
        "/api/method/frappe.auth.get_logged_user",
        headers={
            "X-Frappe-Site": site.site_id,
            "Authorization": f"Bearer {access_token}",
        },
    )

    assert response.status_code == 200
    assert response.data == b"cookie attached"
    assert captured_request["headers"]["Cookie"] == "sid=cookie-123"


def test_proxy_rejects_disallowed_path(client, session):
    user = create_user(session, username="proxypathuser")
    site = create_site(session, user, site_code="C00302")

    response = client.get(
        "/api/private/files/test.txt",
        headers={"X-Frappe-Site": site.site_id},
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "Proxy path is not allowed"


def test_proxy_login_stores_returned_session_cookie(client, session, monkeypatch):
    user = create_user(session, username="proxyloginuser")
    site = create_site(session, user, site_code="C00303")

    def fake_request(method, url, headers, data, allow_redirects):
        return MockUpstreamResponse(
            b'{"message": "Logged in"}',
            200,
            {
                "Content-Type": "application/json",
                "Set-Cookie": (
                    "sid=session-abc; Expires=Wed, 27 Mar 2030 10:00:00 GMT; "
                    "Path=/; Domain=frappe.example.com; HttpOnly"
                ),
            },
        )

    monkeypatch.setattr("app.routes.proxy.requests.request", fake_request)

    response = client.post(
        "/api/method/login",
        headers={"X-Frappe-Site": site.site_id, "Content-Type": "application/json"},
        data=b'{"usr":"demo@example.com","pwd":"secret"}',
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["access_token"]
    assert payload["expires_in"] > 0

    stored_cookie = session.query(Cookie).filter_by(site_id=site.id, cookie_name="sid").one()
    assert stored_cookie.cookie_value == "session-abc"
    assert stored_cookie.domain == "frappe.example.com"
    assert stored_cookie.path == "/"
    assert stored_cookie.expires_at is not None


def test_proxy_login_stores_expired_session_as_unusable_cookie(client, session, monkeypatch):
    user = create_user(session, username="proxyexpireduser")
    site = create_site(session, user, site_code="C00304")

    def fake_request(method, url, headers, data, allow_redirects):
        return MockUpstreamResponse(
            b'{"message": "Logged in"}',
            200,
            {
                "Content-Type": "application/json",
                "Set-Cookie": (
                    "sid=expired-session; Expires=Wed, 27 Mar 2024 10:00:00 GMT; "
                    "Path=/; Domain=frappe.example.com; HttpOnly"
                ),
            },
        )

    monkeypatch.setattr("app.routes.proxy.requests.request", fake_request)

    response = client.post(
        "/api/v1/method/login",
        headers={"X-Frappe-Site": site.site_id, "Content-Type": "application/json"},
        data=b'{"usr":"demo@example.com","pwd":"secret"}',
    )

    assert response.status_code == 200

    stored_cookie = session.query(Cookie).filter_by(site_id=site.id, cookie_name="sid").one()
    assert stored_cookie.cookie_value == "expired-session"
    assert get_valid_cookie(site.id) is None


def test_proxy_routes_store_request_response_logs(client, session, monkeypatch):
    user = create_user(session, username="proxylogger")
    site = create_site(session, user, site_code="C00305")

    def fake_request(method, url, headers, data, allow_redirects):
        return MockUpstreamResponse(
            b'{"proxied": true}',
            207,
            {"Content-Type": "application/json"},
        )

    monkeypatch.setattr("app.routes.proxy.requests.request", fake_request)

    response = client.get(
        "/api/resource/DocType",
        headers={
            "X-Frappe-Site": site.site_id,
            "X-Test-Header": "proxy-log-check",
        },
    )

    assert response.status_code == 207

    log_entry = session.query(Log).order_by(Log.id.desc()).first()
    assert log_entry is not None
    assert log_entry.method == "GET"
    assert log_entry.path == "/api/resource/DocType"
    assert log_entry.response_status == 207
    assert log_entry.site_id == site.id
    assert log_entry.user_id is None
    assert log_entry.headers["X-Frappe-Site"] == site.site_id
    assert log_entry.headers["X-Test-Header"] == "proxy-log-check"
    assert log_entry.timestamp is not None
