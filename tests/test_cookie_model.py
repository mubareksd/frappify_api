from datetime import UTC, datetime, timedelta

from app.models import Cookie, Site, User


def create_user(session, username: str = "cookieowner") -> User:
    user = User(
        username=username,
        password_hash="hashed-password",
        first_name="Cookie",
        middle_name=None,
        last_name="Owner",
        email=f"{username}@example.com",
        email_verified=True,
    )
    session.add(user)
    session.commit()
    return user


def create_site(session, user: User, site_id: str = "C00100") -> Site:
    site = Site(site_id=site_id, base_url="https://cookies.example.com", user_id=user.id)
    session.add(site)
    session.commit()
    return site


def test_store_cookie(session):
    user = create_user(session)
    site = create_site(session, user)
    expires_at = datetime.now(UTC) + timedelta(days=7)

    cookie = Cookie(
        site_id=site.id,
        cookie_name="sessionid",
        cookie_value="abc123",
        expires_at=expires_at,
        path="/",
        domain="example.com",
    )
    session.add(cookie)
    session.commit()

    saved_cookie = session.query(Cookie).filter_by(cookie_name="sessionid").one()

    assert saved_cookie.site_id == site.id
    assert saved_cookie.cookie_value == "abc123"
    assert saved_cookie.path == "/"
    assert saved_cookie.domain == "example.com"
    assert saved_cookie.created_at is not None
    assert saved_cookie.updated_at is not None


def test_retrieve_cookie(session):
    user = create_user(session, username="cookiereader")
    site = create_site(session, user, site_id="C00101")
    cookie = Cookie(
        site_id=site.id,
        cookie_name="csrftoken",
        cookie_value="secure-token",
        expires_at=None,
        path="/account",
        domain="reader.example.com",
    )
    session.add(cookie)
    session.commit()

    found_cookie = session.query(Cookie).filter_by(cookie_name="csrftoken").one()

    assert found_cookie.id == cookie.id
    assert found_cookie.path == "/account"
    assert found_cookie.domain == "reader.example.com"


def test_delete_cookie(session):
    user = create_user(session, username="cookiedeleter")
    site = create_site(session, user, site_id="C00102")
    cookie = Cookie(
        site_id=site.id,
        cookie_name="remember_me",
        cookie_value="persist",
        expires_at=None,
        path="/",
        domain="deleter.example.com",
    )
    session.add(cookie)
    session.commit()

    session.delete(cookie)
    session.commit()

    deleted_cookie = session.query(Cookie).filter_by(cookie_name="remember_me").first()
    assert deleted_cookie is None
