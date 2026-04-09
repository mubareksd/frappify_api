import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app
from app.config import TestConfig
from app.extensions import db
from app.rate_limiter import rate_limiter


@pytest.fixture()
def app():
    os.environ["TEST_DATABASE_URL"] = "sqlite:///:memory:"
    rate_limiter.reset()
    app = create_app(TestConfig)

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()
        rate_limiter.reset()


@pytest.fixture()
def session(app):
    with app.app_context():
        yield db.session


@pytest.fixture()
def client(app):
    return app.test_client()
