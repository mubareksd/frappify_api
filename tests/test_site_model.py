from app.models import Site, User


def create_user(session, username: str = "siteowner") -> User:
    user = User(
        username=username,
        password_hash="hashed-password",
        first_name="Site",
        middle_name=None,
        last_name="Owner",
        email=f"{username}@example.com",
        email_verified=True,
    )
    session.add(user)
    session.commit()
    return user


def test_create_site(session):
    user = create_user(session)

    site = Site(site_id="C00001", base_url="https://example.com", user_id=user.id)
    session.add(site)
    session.commit()

    saved_site = session.query(Site).filter_by(site_id="C00001").one()

    assert saved_site.user_id == user.id
    assert saved_site.base_url == "https://example.com"
    assert saved_site.created_at is not None
    assert saved_site.updated_at is not None


def test_read_site_by_unique_site_id(session):
    user = create_user(session, username="reader")
    site = Site(site_id="C00002", base_url="https://reader.example.com", user_id=user.id)
    session.add(site)
    session.commit()

    found_site = session.query(Site).filter_by(site_id="C00002").one()

    assert found_site.id == site.id
    assert found_site.base_url == "https://reader.example.com"


def test_update_site_base_url(session):
    user = create_user(session, username="updater")
    site = Site(site_id="C00003", base_url="https://old.example.com", user_id=user.id)
    session.add(site)
    session.commit()

    site.base_url = "https://new.example.com"
    session.commit()

    updated_site = session.query(Site).filter_by(site_id="C00003").one()
    assert updated_site.base_url == "https://new.example.com"


def test_delete_site(session):
    user = create_user(session, username="deleter")
    site = Site(site_id="C00004", base_url="https://delete.example.com", user_id=user.id)
    session.add(site)
    session.commit()

    session.delete(site)
    session.commit()

    deleted_site = session.query(Site).filter_by(site_id="C00004").first()
    assert deleted_site is None
