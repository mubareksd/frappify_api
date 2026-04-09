ALLOWED_PROXY_PREFIXES = (
    "/method",
    "/resource",
    "/assets",
    "/v1/method",
    "/v1/resource",
    "/v2/method",
    "/v2/document",
    "/v2/doctype",
)

PROXY_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]

FRAPPE_LOGIN_PATHS = {
    "/method/login",
    "/v1/method/login",
    "/v2/method/login",
}

ALLOWED_WEBSOCKET_PREFIXES = (
    "/socket.io",
    "/ws",
    "/websocket",
)