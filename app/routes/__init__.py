from flask import Blueprint


api_bp = Blueprint("api", __name__)

# Import modules so route decorators are registered on api_bp.
from . import auth, misc, proxy, sites, websocket  # noqa: F401, E402

__all__ = ["api_bp"]