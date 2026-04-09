import os
from datetime import timedelta

from dotenv import load_dotenv


load_dotenv()


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "change-me")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "change-me-too")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(
        minutes=int(os.getenv("JWT_ACCESS_TOKEN_EXPIRES_MINUTES", "15"))
    )
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(
        days=int(os.getenv("JWT_REFRESH_TOKEN_EXPIRES_DAYS", "7"))
    )
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg2://postgres:postgres@localhost:5432/frappe_proxy",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": int(os.getenv("SQLALCHEMY_POOL_RECYCLE_SECONDS", "1800")),
        "pool_timeout": int(os.getenv("SQLALCHEMY_POOL_TIMEOUT_SECONDS", "30")),
    }

    MAIL_SERVER = os.getenv("MAIL_SERVER", "localhost")
    MAIL_PORT = int(os.getenv("MAIL_PORT", "1025"))
    MAIL_USE_TLS = os.getenv("MAIL_USE_TLS", "False").lower() == "true"
    MAIL_USE_SSL = os.getenv("MAIL_USE_SSL", "False").lower() == "true"
    MAIL_USERNAME = os.getenv("MAIL_USERNAME")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = os.getenv("MAIL_DEFAULT_SENDER", "no-reply@frappify.local")
    EMAIL_VERIFICATION_SALT = os.getenv(
        "EMAIL_VERIFICATION_SALT", "email-verification"
    )
    EMAIL_VERIFICATION_MAX_AGE = int(os.getenv("EMAIL_VERIFICATION_MAX_AGE", "86400"))
    PASSWORD_RESET_SALT = os.getenv("PASSWORD_RESET_SALT", "password-reset")
    PASSWORD_RESET_MAX_AGE = int(os.getenv("PASSWORD_RESET_MAX_AGE", "3600"))
    RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "True").lower() == "true"
    RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "100"))
    RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
    RATE_LIMIT_KEY_STRATEGY = os.getenv("RATE_LIMIT_KEY_STRATEGY", "ip").lower()
    RATE_LIMIT_EXEMPT_PATHS = tuple(
        segment.strip()
        for segment in os.getenv("RATE_LIMIT_EXEMPT_PATHS", "/api/health").split(",")
        if segment.strip()
    )
    WEBSOCKET_PROXY_ENABLED = os.getenv("WEBSOCKET_PROXY_ENABLED", "True").lower() == "true"
    WEBSOCKET_PROXY_TIMEOUT_SECONDS = int(os.getenv("WEBSOCKET_PROXY_TIMEOUT_SECONDS", "30"))


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = os.getenv("TEST_DATABASE_URL", "sqlite:///:memory:")
    MAIL_SUPPRESS_SEND = True
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=5)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=1)
    RATE_LIMIT_REQUESTS = 1000
    RATE_LIMIT_EXEMPT_PATHS = ()
