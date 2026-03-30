from flask import Flask, app, g, jsonify, request
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
from sqlalchemy.exc import SQLAlchemyError

from .config import Config
from .extensions import bcrypt, cors, db, jwt, mail, migrate
from . import models
from .models import Log
from .rate_limiter import rate_limiter
from .routes import api_bp


def create_app(config_object: type[Config] = Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_object)
    
    @app.before_request
    def handle_preflight():
        if request.method == "OPTIONS":
            return ("", 204)
    
    @app.after_request
    def add_cors_headers(resp):
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,PATCH,DELETE,OPTIONS"
        return resp

    register_extensions(app)
    register_rate_limiting(app)
    register_request_logging(app)
    register_blueprints(app)

    return app



def register_extensions(app: Flask) -> None:
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    mail.init_app(app)
    bcrypt.init_app(app)
    cors.init_app(app, resources={r"/api/*": {"origins": "*"}})


def register_blueprints(app: Flask) -> None:
    app.register_blueprint(api_bp, url_prefix="/api")


def register_rate_limiting(app: Flask) -> None:
    @app.before_request
    def enforce_rate_limit():
        if not app.config["RATE_LIMIT_ENABLED"]:
            return None
        if not request.path.startswith("/api"):
            return None

        client_ip = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown")
        client_ip = client_ip.split(",")[0].strip()

        allowed = rate_limiter.allow(
            client_ip,
            app.config["RATE_LIMIT_REQUESTS"],
            app.config["RATE_LIMIT_WINDOW_SECONDS"],
        )
        if allowed:
            return None

        return jsonify({"error": "Too Many Requests"}), 429


def register_request_logging(app: Flask) -> None:
    def should_log_path(path: str) -> bool:
        proxy_prefixes = (
            "/api/method",
            "/api/resource",
            "/api/v1/method",
            "/api/v1/resource",
            "/api/v2/method",
            "/api/v2/document",
            "/api/v2/doctype",
        )
        return path.startswith("/api/sites") or path.startswith(proxy_prefixes)

    @app.before_request
    def prepare_request_logging():
        if not should_log_path(request.path):
            return None

        g.should_log_request = True
        g.log_site_id = None
        g.log_user_id = None

        verify_jwt_in_request(optional=True)
        identity = get_jwt_identity()
        if identity is not None:
            g.log_user_id = int(identity)

        return None

    @app.after_request
    def persist_request_log(response):
        if not getattr(g, "should_log_request", False):
            return response

        log_site_id = getattr(g, "log_site_id", None)
        if log_site_id is None:
            return response

        log_entry = Log(
            method=request.method,
            path=request.full_path.rstrip("?"),
            headers=dict(request.headers),
            ip_address=request.headers.get("X-Forwarded-For", request.remote_addr or "unknown").split(",")[0].strip(),
            mac_address=request.headers.get("X-Forwarded-Mac", None),
            response_status=response.status_code,
            site_id=log_site_id,
            user_id=getattr(g, "log_user_id", None),
        )
        try:
            db.session.add(log_entry)
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()

        return response

    @app.teardown_request
    def rollback_session_on_exception(exc):
        if exc is not None:
            db.session.rollback()
