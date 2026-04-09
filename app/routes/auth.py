from http import HTTPStatus

from flask import jsonify, request
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    get_jwt_identity,
    jwt_required,
)

from ..auth import (
    generate_password_reset_token,
    send_password_reset_email,
    verify_email_token,
    verify_password_reset_token,
)
from ..extensions import db
from ..models import User
from . import api_bp


@api_bp.post("/auth/register")
def register():
    payload = request.get_json(silent=True) or {}
    required_fields = [
        "username",
        "password",
        "first_name",
        "last_name",
        "email",
    ]
    missing_fields = [field for field in required_fields if not payload.get(field)]

    if missing_fields:
        return (
            jsonify({"error": f"Missing required fields: {', '.join(missing_fields)}"}),
            HTTPStatus.BAD_REQUEST,
        )

    existing_user = User.query.filter(
        (User.username == payload["username"]) | (User.email == payload["email"])
    ).first()
    if existing_user:
        return (
            jsonify({"error": "A user with that username or email already exists"}),
            HTTPStatus.CONFLICT,
        )

    user = User(
        username=payload["username"],
        first_name=payload["first_name"],
        middle_name=payload.get("middle_name"),
        last_name=payload["last_name"],
        email=payload["email"],
        email_verified=False,
    )
    user.set_password(payload["password"])

    db.session.add(user)
    db.session.commit()

    return (
        jsonify(
            {
                "message": "Registration successful. Please verify your email.",
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "email_verified": user.email_verified,
                },
            }
        ),
        HTTPStatus.CREATED,
    )


@api_bp.get("/auth/verify-email")
def verify_email():
    token = request.args.get("token")
    if not token:
        return jsonify({"error": "Verification token is required"}), HTTPStatus.BAD_REQUEST

    user_id = verify_email_token(token)
    if user_id is None:
        return jsonify({"error": "Invalid or expired verification token"}), HTTPStatus.BAD_REQUEST

    user = db.session.get(User, user_id)
    if user is None:
        return jsonify({"error": "User not found"}), HTTPStatus.NOT_FOUND

    user.email_verified = True
    db.session.commit()

    return jsonify({"message": "Email verified successfully"}), HTTPStatus.OK


@api_bp.post("/auth/login")
def login():
    payload = request.get_json(silent=True) or {}
    username = payload.get("username")
    password = payload.get("password")

    if not username or not password:
        return (
            jsonify({"error": "Username and password are required"}),
            HTTPStatus.BAD_REQUEST,
        )

    user = User.query.filter_by(username=username).first()
    if user is None or not user.check_password(password):
        return jsonify({"error": "Invalid credentials"}), HTTPStatus.UNAUTHORIZED

    access_token = create_access_token(identity=str(user.id))
    refresh_token = create_refresh_token(identity=str(user.id))

    return (
        jsonify(
            {
                "access_token": access_token,
                "access_token_expires_in": 15 * 60,
                "refresh_token": refresh_token,
                "refresh_token_expires_in": 7 * 24 * 60 * 60,
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "email_verified": user.email_verified,
                },
            }
        ),
        HTTPStatus.OK,
    )


@api_bp.post("/auth/refresh")
@jwt_required(refresh=True)
def refresh():
    access_token = create_access_token(identity=get_jwt_identity())
    return jsonify({"access_token": access_token, "access_token_expires_in": 15 * 60}), HTTPStatus.OK


@api_bp.post("/auth/forgot-password")
def forgot_password():
    payload = request.get_json(silent=True) or {}
    email = payload.get("email")

    if not email:
        return jsonify({"error": "Email is required"}), HTTPStatus.BAD_REQUEST

    user = User.query.filter_by(email=email).first()
    if user is not None:
        token = generate_password_reset_token(user.id)
        send_password_reset_email(user.email, token)

    return (
        jsonify(
            {
                "message": (
                    "If an account with that email exists, a password reset email has been sent."
                )
            }
        ),
        HTTPStatus.OK,
    )


@api_bp.post("/auth/reset-password")
def reset_password():
    payload = request.get_json(silent=True) or {}
    token = payload.get("token")
    new_password = payload.get("password")

    if not token or not new_password:
        return (
            jsonify({"error": "Token and password are required"}),
            HTTPStatus.BAD_REQUEST,
        )

    user_id = verify_password_reset_token(token)
    if user_id is None:
        return jsonify({"error": "Invalid or expired reset token"}), HTTPStatus.BAD_REQUEST

    user = db.session.get(User, user_id)
    if user is None:
        return jsonify({"error": "User not found"}), HTTPStatus.NOT_FOUND

    user.set_password(new_password)
    db.session.commit()

    return jsonify({"message": "Password reset successfully"}), HTTPStatus.OK