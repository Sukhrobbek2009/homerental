import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app import models, storage
from app.config import Settings, settings
from app.database import SessionLocal
from app.security import hash_password

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---- SECRET_KEY and demo seeding -----------------------------------------------


def _start_config(tmp_path, secret_key: str | None) -> subprocess.CompletedProcess:
    # Run from an empty directory so backend/.env isn't read.
    env = {k: v for k, v in os.environ.items() if k != "SECRET_KEY"}
    env["PYTHONPATH"] = str(BACKEND_DIR)
    if secret_key is not None:
        env["SECRET_KEY"] = secret_key
    return subprocess.run(
        [sys.executable, "-c", "import app.config"], cwd=tmp_path, env=env, capture_output=True, text=True
    )


@pytest.mark.parametrize(
    "secret_key",
    [None, "", "short-key", "change-this-to-a-long-random-secret", "dev-only-secret-change-me"],
)
def test_server_refuses_to_start_without_a_private_secret_key(tmp_path, secret_key):
    result = _start_config(tmp_path, secret_key)
    assert result.returncode != 0
    assert "SECRET_KEY must be set" in result.stderr


def test_server_starts_with_a_proper_secret_key(tmp_path):
    result = _start_config(tmp_path, "k" * 48)
    assert result.returncode == 0, result.stderr


def test_demo_seeding_is_off_unless_asked_for(monkeypatch):
    monkeypatch.delenv("SEED_DEMO_DATA", raising=False)
    assert Settings(_env_file=None).seed_demo_data is False


# ---- Passwords -------------------------------------------------------------------


@pytest.mark.parametrize("password", ["a1" * 36 + "b", "é" * 36 + "a1"])
def test_signup_rejects_passwords_over_72_bytes(client, password):
    response = client.post(
        "/api/auth/signup",
        json={"full_name": "Long Password", "email": "long-pw@example.com", "password": password},
    )
    assert response.status_code == 422
    assert "too long" in response.text


def test_signup_accepts_exactly_72_bytes(client):
    response = client.post(
        "/api/auth/signup",
        json={"full_name": "Max Password", "email": "max-pw@example.com", "password": "a1" * 36},
    )
    assert response.status_code == 201, response.text


def test_existing_account_with_long_password_can_still_log_in(client):
    long_password = "x9" * 50  # 100 bytes, from before signup capped the length
    db = SessionLocal()
    try:
        db.add(models.User(
            full_name="Legacy User", email="legacy-long@example.com",
            password_hash=hash_password(long_password), role=models.UserRole.renter,
        ))
        db.commit()
    finally:
        db.close()

    ok = client.post("/api/auth/login", json={"email": "legacy-long@example.com", "password": long_password})
    wrong = client.post("/api/auth/login", json={"email": "legacy-long@example.com", "password": "x9" * 35 + "zz"})

    assert ok.status_code == 200
    assert wrong.status_code == 401


# ---- Listing image URLs --------------------------------------------------------------


def _listing_body(**overrides) -> dict:
    body = {"listing_type": "home", "title": "Safe home", "location": "Austin, TX", "price": 100, "price_unit": "night"}
    body.update(overrides)
    return body


@pytest.mark.parametrize(
    "image_url",
    ["javascript:alert(1)", "data:image/png;base64,AAAA", "ftp://example.com/a.jpg", "https://example.com/" + "a" * 2100],
)
def test_listing_image_url_must_be_a_web_url(client, host, image_url):
    created = client.post("/api/listings", json=_listing_body(image_url=image_url), headers=host["headers"])
    assert created.status_code == 422

    listing = client.post("/api/listings", json=_listing_body(), headers=host["headers"]).json()
    updated = client.patch(f"/api/listings/{listing['id']}", json={"image_url": image_url}, headers=host["headers"])
    assert updated.status_code == 422


def test_listing_image_url_accepts_https(client, host):
    response = client.post(
        "/api/listings", json=_listing_body(image_url="https://cdn.example.com/p.jpg"), headers=host["headers"]
    )
    assert response.status_code == 201
    assert response.json()["image_url"] == "https://cdn.example.com/p.jpg"


def test_existing_listing_with_old_style_image_still_loads(client, host):
    listing = client.post("/api/listings", json=_listing_body(location="Legacyville"), headers=host["headers"]).json()
    db = SessionLocal()
    try:
        db.get(models.Listing, listing["id"]).image_url = "data:image/png;base64,AAAA"
        db.commit()
    finally:
        db.close()

    assert client.get(f"/api/listings/{listing['id']}").status_code == 200
    assert client.get("/api/listings", params={"city": "Legacyville"}).status_code == 200


# ---- Bookings in the past ---------------------------------------------------------------


def test_bookings_cannot_start_in_the_past(client, host, renter):
    listing = client.post("/api/listings", json=_listing_body(), headers=host["headers"]).json()

    server_today = datetime.now(timezone.utc).date()  # the rule is relative to the server's UTC date

    def book(start: int):
        return client.post(
            "/api/bookings",
            json={"listing_id": listing["id"], "start_date": str(server_today + timedelta(days=start)),
                  "end_date": str(server_today + timedelta(days=start + 2))},
            headers=renter["headers"],
        )

    past = book(-10)
    assert past.status_code == 422
    assert "past" in past.text
    assert book(-1).status_code == 201  # time-zone slack
    assert book(5).status_code == 201


# ---- Photos of deleted listings -----------------------------------------------------------


class _FakeS3:
    def __init__(self):
        self.objects = {}

    def put_object(self, Bucket, Key, Body, ContentType):
        self.objects[Key] = Body

    def delete_object(self, Bucket, Key):
        self.objects.pop(Key, None)


def test_deleting_a_listing_removes_its_photos_from_storage(client, host, monkeypatch):
    s3 = _FakeS3()
    for name, value in {"s3_endpoint": "https://s3.example.com", "s3_bucket": "photos", "s3_key": "k", "s3_secret": "s", "s3_public_url": ""}.items():
        monkeypatch.setattr(settings, name, value)
    monkeypatch.setattr(storage, "_client", lambda: s3)
    listing = client.post("/api/listings", json=_listing_body(), headers=host["headers"]).json()
    jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 64
    for _ in range(2):
        response = client.post(
            f"/api/listings/{listing['id']}/photos", files={"photo": ("p.jpg", jpeg, "image/jpeg")}, headers=host["headers"]
        )
        assert response.status_code == 201, response.text
    assert len(s3.objects) == 2

    assert client.delete(f"/api/listings/{listing['id']}", headers=host["headers"]).json()["deleted"] is True

    assert s3.objects == {}


def test_key_from_url_ignores_foreign_urls(monkeypatch):
    for name, value in {"s3_endpoint": "https://s3.example.com", "s3_bucket": "photos", "s3_key": "k", "s3_secret": "s", "s3_public_url": ""}.items():
        monkeypatch.setattr(settings, name, value)
    assert storage.key_from_url("https://s3.example.com/photos/listings/a/b.jpg") == "listings/a/b.jpg"
    assert storage.key_from_url("https://elsewhere.example.com/photos/listings/a/b.jpg") is None
    assert storage.key_from_url("https://s3.example.com/other-bucket/x.jpg") is None


# ---- City search wildcards ---------------------------------------------------------------------


def test_city_search_treats_wildcards_literally(client, host):
    client.post("/api/listings", json=_listing_body(location="Wildcard_Town"), headers=host["headers"])
    client.post("/api/listings", json=_listing_body(location="WildcardXTown"), headers=host["headers"])

    underscore = client.get("/api/listings", params={"city": "Wildcard_Town"}).json()
    percent = client.get("/api/listings", params={"city": "%"}).json()

    assert [item["location"] for item in underscore] == ["Wildcard_Town"]
    assert percent == []
