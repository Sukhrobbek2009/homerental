import os

os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production-use")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SEED_DEMO_DATA", "false")

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
    db_path = "test.db"
    if os.path.exists(db_path):
        os.remove(db_path)


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
