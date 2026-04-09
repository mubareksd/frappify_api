from flask import jsonify

from ..models import Cookie, Log, Site, User
from . import api_bp


@api_bp.get("/hello")
def hello_world():
    return jsonify({"message": "Hello World from Flask"})


@api_bp.get("/health")
def health():
    return jsonify({"status": "ok"})


@api_bp.get("/dashboard/summary")
def dashboard_summary():
    return jsonify(
        {
            "counts": {
                "users": User.query.count(),
                "sites": Site.query.count(),
                "cookies": Cookie.query.count(),
                "logs": Log.query.count(),
            }
        }
    )