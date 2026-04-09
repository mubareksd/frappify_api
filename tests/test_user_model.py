from app.models import User


def test_insert_and_retrieve_user(session):
    user = User(
        username="alice",
        password_hash="hashed-password",
        first_name="Alice",
        middle_name="Jane",
        last_name="Doe",
        email="alice@example.com",
        email_verified=True,
    )

    session.add(user)
    session.commit()

    saved_user = session.query(User).filter_by(username="alice").one()

    assert saved_user.password_hash == "hashed-password"
    assert saved_user.first_name == "Alice"
    assert saved_user.middle_name == "Jane"
    assert saved_user.last_name == "Doe"
    assert saved_user.email == "alice@example.com"
    assert saved_user.email_verified is True
    assert saved_user.created_at is not None
    assert saved_user.updated_at is not None
