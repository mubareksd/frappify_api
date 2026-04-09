from datetime import UTC, datetime, timedelta

from app.cookies import delete_cookie, get_valid_cookie, store_cookie
from app.models import Cookie, Site, User


def create_user(session, username: str = "cookieutilowner") -> User:
    user = User(
        username=username,
        password_hash="hashed-password",
        first_name="Cookie",
        middle_name=None,
        last_name="Utility",
        email=f"{username}@example.com",
        email_verified=True,
    )
    session.add(user)
    session.commit()
    return user


def create_site(session, user: User, site_code: str = "C00200") -> Site:
    site = Site(site_id=site_code, base_url="https://util.example.com", user_id=user.id)
    session.add(site)
    session.commit()
    return site


def test_store_cookie_saves_cookie_to_database(session):
    user = create_user(session)
    site = create_site(session, user)
    expires_at = datetime.now(UTC) + timedelta(hours=1)

    saved_cookie = store_cookie(
        site.id,
        {
            "cookie_name": "sessionid",
            "cookie_value": "value-123",
            "expires_at": expires_at,
            "path": "/",
            "domain": "example.com",
        },
    )

    stored = session.query(Cookie).filter_by(site_id=site.id, cookie_name="sessionid").one()
    assert saved_cookie.id == stored.id
    assert stored.cookie_value == "value-123"
    assert stored.expires_at == expires_at.replace(tzinfo=None)
    assert stored.domain == "example.com"


def test_get_valid_cookie_returns_only_unexpired_cookie(session):
    user = create_user(session, username="validcookieuser")
    site = create_site(session, user, site_code="C00201")

    store_cookie(
        site.id,
        {
            "cookie_name": "expired_cookie",
            "cookie_value": "expired",
            "expires_at": datetime.now(UTC) - timedelta(minutes=5),
            "path": "/",
            "domain": "expired.example.com",
        },
    )
    valid_cookie = store_cookie(
        site.id,
        {
            "cookie_name": "valid_cookie",
            "cookie_value": "fresh",
            "expires_at": datetime.now(UTC) + timedelta(minutes=30),
            "path": "/dashboard",
            "domain": "valid.example.com",
        },
    )

    found_cookie = get_valid_cookie(site.id)

    assert found_cookie is not None
    assert found_cookie.id == valid_cookie.id
    assert found_cookie.cookie_name == "valid_cookie"
    assert found_cookie.cookie_value == "fresh"


def test_delete_cookie_removes_specific_cookie(session):
    user = create_user(session, username="deletecookieuser")
    site = create_site(session, user, site_code="C00202")
    store_cookie(
        site.id,
        {
            "cookie_name": "remember_me",
            "cookie_value": "persist",
            "expires_at": None,
            "path": "/",
            "domain": "delete.example.com",
        },
    )

    deleted = delete_cookie(site.id, "remember_me")

    assert deleted is True
    assert session.query(Cookie).filter_by(site_id=site.id, cookie_name="remember_me").first() is None
