from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from flask import current_app, url_for
from flask_mail import Message

from .extensions import mail


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"])


def _generate_token(user_id: int, salt: str) -> str:
    return _serializer().dumps({"user_id": user_id}, salt=salt)


def _verify_token(token: str, salt: str, max_age: int) -> int | None:
    try:
        payload = _serializer().loads(token, salt=salt, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None

    return payload.get("user_id")


def generate_email_verification_token(user_id: int) -> str:
    return _generate_token(user_id, current_app.config["EMAIL_VERIFICATION_SALT"])


def verify_email_token(token: str) -> int | None:
    return _verify_token(
        token,
        current_app.config["EMAIL_VERIFICATION_SALT"],
        current_app.config["EMAIL_VERIFICATION_MAX_AGE"],
    )


def generate_password_reset_token(user_id: int) -> str:
    return _generate_token(user_id, current_app.config["PASSWORD_RESET_SALT"])


def verify_password_reset_token(token: str) -> int | None:
    return _verify_token(
        token,
        current_app.config["PASSWORD_RESET_SALT"],
        current_app.config["PASSWORD_RESET_MAX_AGE"],
    )


def send_verification_email(recipient: str, token: str) -> None:
    verification_url = url_for("api.verify_email", token=token, _external=True)
    message = Message(
        subject="Verify your email",
        recipients=[recipient],
        body=(
            "Welcome to Frappify.\n\n"
            f"Verify your email by opening: {verification_url}\n"
        ),
    )
    mail.send(message)


def send_password_reset_email(recipient: str, token: str) -> None:
    reset_url = url_for("api.reset_password", token=token, _external=True)
    message = Message(
        subject="Reset your password",
        recipients=[recipient],
        body=(
            "We received a request to reset your password.\n\n"
            f"Reset your password by opening: {reset_url}\n"
        ),
    )
    mail.send(message)
