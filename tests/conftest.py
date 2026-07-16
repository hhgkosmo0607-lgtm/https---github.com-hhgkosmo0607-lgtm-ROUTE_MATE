import pytest

from app import create_app
from app.config import TestConfig
from app.extensions import db as _db


@pytest.fixture
def app():
    flask_app = create_app(TestConfig)
    with flask_app.app_context():
        _db.create_all()
        yield flask_app
        _db.session.remove()
        _db.drop_all()


class ApiClient:
    """Wraps Flask's test client and auto-attaches the CSRF header on
    state-changing requests, mirroring how a real frontend fetches
    GET /api/csrf-token before mutating calls (설계서 7.1/11.2)."""

    def __init__(self, raw_client):
        self.raw = raw_client

    def _csrf_headers(self):
        resp = self.raw.get("/api/csrf-token")
        token = resp.get_json()["data"]["csrf_token"]
        return {"X-CSRF-Token": token}

    def get(self, *args, **kwargs):
        return self.raw.get(*args, **kwargs)

    def post(self, *args, **kwargs):
        headers = kwargs.pop("headers", {}) or {}
        headers.update(self._csrf_headers())
        return self.raw.post(*args, headers=headers, **kwargs)

    def put(self, *args, **kwargs):
        headers = kwargs.pop("headers", {}) or {}
        headers.update(self._csrf_headers())
        return self.raw.put(*args, headers=headers, **kwargs)

    def delete(self, *args, **kwargs):
        headers = kwargs.pop("headers", {}) or {}
        headers.update(self._csrf_headers())
        return self.raw.delete(*args, headers=headers, **kwargs)


@pytest.fixture
def client(app):
    return ApiClient(app.test_client())
