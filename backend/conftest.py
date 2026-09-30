import os
import shutil
import tempfile
import uuid

# Always a fresh SQLite file in its own temp directory, set before the app is
# imported. This is deliberately not setdefault: a DATABASE_URL left in the
# shell (e.g. production, for a migration) must never be where the tests
# create and drop their tables, and two runs at once must not share a file.
_TEST_DB_DIR = tempfile.mkdtemp(prefix="homerental-tests-")
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_TEST_DB_DIR, 'test.db')}"
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production-use")
os.environ["SEED_DEMO_DATA"] = "false"
# Tests sign up many users from one client address; test_hardening.py turns
# the limit back on where it is being tested.
os.environ["AUTH_RATE_LIMIT_PER_MINUTE"] = "0"

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

from app import models
from app.database import Base, engine
from app.deps import require_role
from app.main import app
from app.security import hash_password
from app.database import SessionLocal


# No production route is host-only yet, so tests exercise `require_role`
# through a throwaway probe route rather than asserting on real business
# behavior that might change independently of the auth dependency itself.
@app.get("/api/_test/host-only")
def _host_only_probe(current_user: models.User = Depends(require_role("host"))) -> dict:
    return {"ok": True, "user_id": current_user.id}


@pytest.fixture(scope="session", autouse=True)
def _test_database():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    shutil.rmtree(_TEST_DB_DIR, ignore_errors=True)


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def signup(client):
    def _signup(email: str, role: str = "renter", password: str = "password1", full_name: str = "Test User") -> dict:
        response = client.post(
            "/api/auth/signup",
            json={"full_name": full_name, "email": email, "password": password, "role": role},
        )
        assert response.status_code == 201, response.text
        return response.json()

    return _signup


@pytest.fixture()
def make_admin(client):
    def _make_admin(email: str = "admin@example.com", password: str = "password1") -> str:
        db = SessionLocal()
        try:
            user = models.User(
                full_name="Admin User",
                email=email,
                password_hash=hash_password(password),
                role=models.UserRole.admin,
            )
            db.add(user)
            db.commit()
        finally:
            db.close()

        response = client.post("/api/auth/login", json={"email": email, "password": password})
        assert response.status_code == 200, response.text
        return response.json()["access_token"]

    return _make_admin


def _unique_email(role: str) -> str:
    return f"{role}-{uuid.uuid4().hex[:10]}@example.com"


@pytest.fixture()
def renter(signup) -> dict:
    """A fresh renter: {"token", "user", "headers"}."""
    tokens = signup(_unique_email("renter"), role="renter", full_name="Rita Renter")
    return {"token": tokens["access_token"], "user": tokens["user"], "headers": {"Authorization": f"Bearer {tokens['access_token']}"}}


@pytest.fixture()
def host(signup) -> dict:
    """A fresh host: {"token", "user", "headers"}."""
    tokens = signup(_unique_email("host"), role="host", full_name="Hank Host")
    return {"token": tokens["access_token"], "user": tokens["user"], "headers": {"Authorization": f"Bearer {tokens['access_token']}"}}


@pytest.fixture()
def admin(make_admin) -> dict:
    """A fresh admin: {"token", "headers"}."""
    token = make_admin(_unique_email("admin"))
    return {"token": token, "headers": {"Authorization": f"Bearer {token}"}}
