import re

from flask_jwt_extended import decode_token

from app.extensions import mail
from app.models import User


def extract_token(body: str) -> str:
    match = re.search(r"token=([^\s]+)", body)
    assert match is not None
    return match.group(1)


def test_register_user_creates_user_and_sends_verification_email(app, client, session):
    payload = {
        "username": "alice",
        "password": "S3curePass!",
        "first_name": "Alice",
        "middle_name": "Jane",
        "last_name": "Doe",
        "email": "alice@example.com",
    }

    with mail.record_messages() as outbox:
        response = client.post("/api/auth/register", json=payload)

    assert response.status_code == 201
    data = response.get_json()
    assert data["user"]["email_verified"] is False

    saved_user = session.query(User).filter_by(username="alice").one()
    assert saved_user.email == "alice@example.com"
    assert saved_user.password_hash != payload["password"]
    assert saved_user.password_hash.startswith("$2")
    assert saved_user.check_password(payload["password"]) is True

    assert len(outbox) == 1
    assert outbox[0].recipients == ["alice@example.com"]
    assert "Verify your email" in outbox[0].subject
    assert "/api/auth/verify-email?token=" in outbox[0].body


def test_verify_email_marks_user_as_verified(app, client, session):
    payload = {
        "username": "bruce",
        "password": "S3curePass!",
        "first_name": "Bruce",
        "middle_name": None,
        "last_name": "Wayne",
        "email": "bruce@example.com",
    }

    with mail.record_messages() as outbox:
        register_response = client.post("/api/auth/register", json=payload)

    assert register_response.status_code == 201
    token = extract_token(outbox[0].body)

    verify_response = client.get(f"/api/auth/verify-email?token={token}")

    assert verify_response.status_code == 200
    assert verify_response.get_json()["message"] == "Email verified successfully"

    verified_user = session.query(User).filter_by(username="bruce").one()
    assert verified_user.email_verified is True


def test_login_returns_access_and_refresh_tokens(client, session):
    user = User(
        username="clark",
        first_name="Clark",
        middle_name=None,
        last_name="Kent",
        email="clark@example.com",
        email_verified=True,
    )
    user.set_password("Str0ngPass!")
    session.add(user)
    session.commit()

    response = client.post(
        "/api/auth/login",
        json={"username": "clark", "password": "Str0ngPass!"},
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["token_type"] == "Bearer"
    assert data["user"]["username"] == "clark"
    assert "access_token" in data
    assert "refresh_token" in data

    access_payload = decode_token(data["access_token"])
    refresh_payload = decode_token(data["refresh_token"])

    assert access_payload["sub"] == str(user.id)
    assert access_payload["type"] == "access"
    assert refresh_payload["sub"] == str(user.id)
    assert refresh_payload["type"] == "refresh"


def test_login_rejects_invalid_credentials(client, session):
    user = User(
        username="diana",
        first_name="Diana",
        middle_name=None,
        last_name="Prince",
        email="diana@example.com",
        email_verified=True,
    )
    user.set_password("Amaz0nPass!")
    session.add(user)
    session.commit()

    response = client.post(
        "/api/auth/login",
        json={"username": "diana", "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert response.get_json()["error"] == "Invalid credentials"


def test_refresh_returns_new_access_token(client, session):
    user = User(
        username="barry",
        first_name="Barry",
        middle_name=None,
        last_name="Allen",
        email="barry@example.com",
        email_verified=True,
    )
    user.set_password("FastPass123!")
    session.add(user)
    session.commit()

    login_response = client.post(
        "/api/auth/login",
        json={"username": "barry", "password": "FastPass123!"},
    )
    refresh_token = login_response.get_json()["refresh_token"]

    refresh_response = client.post(
        "/api/auth/refresh",
        headers={"Authorization": f"Bearer {refresh_token}"},
    )

    assert refresh_response.status_code == 200
    data = refresh_response.get_json()
    assert data["token_type"] == "Bearer"
    assert "access_token" in data

    access_payload = decode_token(data["access_token"])
    assert access_payload["sub"] == str(user.id)
    assert access_payload["type"] == "access"


def test_forgot_password_sends_reset_email(client, session):
    user = User(
        username="arthur",
        first_name="Arthur",
        middle_name=None,
        last_name="Curry",
        email="arthur@example.com",
        email_verified=True,
    )
    user.set_password("OceanPass123!")
    session.add(user)
    session.commit()

    with mail.record_messages() as outbox:
        response = client.post(
            "/api/auth/forgot-password",
            json={"email": "arthur@example.com"},
        )

    assert response.status_code == 200
    assert "password reset email has been sent" in response.get_json()["message"]
    assert len(outbox) == 1
    assert outbox[0].recipients == ["arthur@example.com"]
    assert outbox[0].subject == "Reset your password"
    assert "/api/auth/reset-password?token=" in outbox[0].body


def test_reset_password_updates_password_and_allows_login(client, session):
    user = User(
        username="hal",
        first_name="Hal",
        middle_name=None,
        last_name="Jordan",
        email="hal@example.com",
        email_verified=True,
    )
    user.set_password("OldPass123!")
    session.add(user)
    session.commit()

    with mail.record_messages() as outbox:
        forgot_response = client.post(
            "/api/auth/forgot-password",
            json={"email": "hal@example.com"},
        )

    assert forgot_response.status_code == 200
    token = extract_token(outbox[0].body)

    reset_response = client.post(
        "/api/auth/reset-password",
        json={"token": token, "password": "NewPass456!"},
    )

    assert reset_response.status_code == 200
    assert reset_response.get_json()["message"] == "Password reset successfully"

    updated_user = session.query(User).filter_by(username="hal").one()
    assert updated_user.check_password("OldPass123!") is False
    assert updated_user.check_password("NewPass456!") is True

    login_response = client.post(
        "/api/auth/login",
        json={"username": "hal", "password": "NewPass456!"},
    )
    assert login_response.status_code == 200
