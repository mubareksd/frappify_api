from app import create_app
from app.config import TestConfig
from app.extensions import db
from app.rate_limiter import rate_limiter


class RateLimitedTestConfig(TestConfig):
    RATE_LIMIT_REQUESTS = 2
    RATE_LIMIT_WINDOW_SECONDS = 60


def test_rate_limiter_returns_429_after_limit_exceeded():
    rate_limiter.reset()
    app = create_app(RateLimitedTestConfig)

    with app.app_context():
        db.create_all()
        client = app.test_client()

        first_response = client.get("/api/hello", environ_base={"REMOTE_ADDR": "10.0.0.1"})
        second_response = client.get("/api/hello", environ_base={"REMOTE_ADDR": "10.0.0.1"})
        third_response = client.get("/api/hello", environ_base={"REMOTE_ADDR": "10.0.0.1"})

        assert first_response.status_code == 200
        assert second_response.status_code == 200
        assert third_response.status_code == 429
        assert third_response.get_json()["error"] == "Too Many Requests"

        db.drop_all()
        rate_limiter.reset()


def test_rate_limiter_tracks_ips_separately():
    rate_limiter.reset()
    app = create_app(RateLimitedTestConfig)

    with app.app_context():
        db.create_all()
        client = app.test_client()

        limited_response = None
        for _ in range(3):
            limited_response = client.get("/api/hello", environ_base={"REMOTE_ADDR": "10.0.0.2"})

        other_ip_response = client.get("/api/hello", environ_base={"REMOTE_ADDR": "10.0.0.3"})

        assert limited_response is not None
        assert limited_response.status_code == 429
        assert other_ip_response.status_code == 200

        db.drop_all()
        rate_limiter.reset()
