from threading import Event, Thread
from urllib.parse import urlparse

from flask import current_app, request
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
from websocket import WebSocketConnectionClosedException, create_connection

from ..cookies import get_valid_cookie_by_id
from ..extensions import sock
from ..models import Site
from .utils import extract_client_ip, is_allowed_websocket_path, is_ip_allowed


@sock.route("/api/ws/<path:path>")
def proxy_websocket_connection(ws, path: str):
    if not current_app.config.get("WEBSOCKET_PROXY_ENABLED", True):
        ws.close()
        return

    if not is_allowed_websocket_path(path):
        ws.close()
        return

    target_site_id = request.headers.get("X-Frappe-Site")
    if not target_site_id:
        ws.close()
        return

    site = Site.query.filter_by(site_id=target_site_id).first()
    if site is None:
        ws.close()
        return

    client_ip = extract_client_ip()
    if site.enable_ip_filter and not client_ip:
        ws.close()
        return
    if not is_ip_allowed(site, client_ip):
        ws.close()
        return

    proxied_path = path.lstrip("/")
    parsed_base = urlparse(site.base_url)
    upstream_scheme = "wss" if parsed_base.scheme == "https" else "ws"
    upstream_url = f"{upstream_scheme}://{parsed_base.netloc}/{proxied_path}"
    if request.query_string:
        upstream_url = f"{upstream_url}?{request.query_string.decode()}"

    excluded_headers = {
        "host",
        "connection",
        "upgrade",
        "sec-websocket-key",
        "sec-websocket-version",
        "sec-websocket-extensions",
        "x-frappe-site",
        "content-length",
    }
    upstream_headers = [
        f"{key}: {value}"
        for key, value in request.headers.items()
        if key.lower() not in excluded_headers
    ]

    authorization_header = request.headers.get("Authorization")
    if authorization_header and authorization_header.startswith("Bearer "):
        try:
            verify_jwt_in_request()
            identity = get_jwt_identity()
            if identity is None:
                ws.close()
                return
            cookie = get_valid_cookie_by_id(site.id, int(identity))
            if cookie is None:
                ws.close()
                return
            upstream_headers.append(f"Cookie: {cookie.cookie_name}={cookie.cookie_value}")
        except Exception:
            ws.close()
            return

    try:
        upstream_ws = create_connection(
            upstream_url,
            header=upstream_headers,
            timeout=current_app.config.get("WEBSOCKET_PROXY_TIMEOUT_SECONDS", 30),
            enable_multithread=True,
        )
    except Exception:
        ws.close()
        return

    stop_event = Event()

    def client_to_upstream() -> None:
        try:
            while not stop_event.is_set():
                message = ws.receive()
                if message is None:
                    break
                if isinstance(message, bytes):
                    upstream_ws.send_binary(message)
                else:
                    upstream_ws.send(message)
        except Exception:
            pass
        finally:
            stop_event.set()

    def upstream_to_client() -> None:
        try:
            while not stop_event.is_set():
                message = upstream_ws.recv()
                if message is None:
                    break
                ws.send(message)
        except (WebSocketConnectionClosedException, OSError):
            pass
        finally:
            stop_event.set()

    to_upstream = Thread(target=client_to_upstream, daemon=True)
    to_client = Thread(target=upstream_to_client, daemon=True)
    to_upstream.start()
    to_client.start()
    to_upstream.join()
    to_client.join()

    try:
        upstream_ws.close()
    except Exception:
        pass

    try:
        ws.close()
    except Exception:
        pass