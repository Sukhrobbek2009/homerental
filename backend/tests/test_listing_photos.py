import pytest

from app import storage
from app.config import settings

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 64
GIF = b"GIF89a" + b"\x00" * 64


class FakeS3:
    def __init__(self):
        self.objects = {}

    def put_object(self, Bucket, Key, Body, ContentType):
        self.objects[Key] = (Bucket, Body, ContentType)

    def delete_object(self, Bucket, Key):
        self.objects.pop(Key, None)


@pytest.fixture()
def fake_s3(monkeypatch):
    s3 = FakeS3()
    monkeypatch.setattr(settings, "s3_endpoint", "https://s3.example.com")
    monkeypatch.setattr(settings, "s3_bucket", "photos")
    monkeypatch.setattr(settings, "s3_key", "key")
    monkeypatch.setattr(settings, "s3_secret", "secret")
    monkeypatch.setattr(settings, "s3_public_url", "")
    monkeypatch.setattr(storage, "_client", lambda: s3)
    return s3


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def host_listing(client, signup):
    def _make(email: str):
        token = signup(email, role="host")["access_token"]
        response = client.post(
            "/api/listings",
            json={"listing_type": "home", "title": "Test home", "location": "Austin, TX", "price": 100, "price_unit": "night"},
            headers=_auth(token),
        )
        assert response.status_code == 201, response.text
        return token, response.json()["id"]

    return _make


def _upload(client, listing_id, token, data, filename="photo.jpg", content_type="image/jpeg"):
    return client.post(
        f"/api/listings/{listing_id}/photos",
        files={"photo": (filename, data, content_type)},
        headers=_auth(token),
    )


def test_owner_upload_stores_random_name_and_appends_url(client, host_listing, fake_s3):
    token, listing_id = host_listing("photo-owner@example.com")

    response = _upload(client, listing_id, token, JPEG, filename="../../my house.jpg")

    assert response.status_code == 201, response.text
    body = response.json()
    [key] = fake_s3.objects
    assert key.startswith(f"listings/{listing_id}/") and key.endswith(".jpg")
    assert "my house" not in key and ".." not in key
    assert fake_s3.objects[key] == ("photos", JPEG, "image/jpeg")
    assert body["photos"] == [f"https://s3.example.com/photos/{key}"]
    assert body["image_url"] == body["photos"][0]


@pytest.mark.parametrize("data,content_type,ext", [(PNG, "image/png", "png"), (WEBP, "image/webp", "webp")])
def test_png_and_webp_are_accepted(client, host_listing, fake_s3, data, content_type, ext):
    token, listing_id = host_listing(f"photo-{ext}@example.com")

    response = _upload(client, listing_id, token, data, filename="x.jpg", content_type="image/jpeg")

    assert response.status_code == 201, response.text
    [(bucket, _, stored_type)] = fake_s3.objects.values()
    assert stored_type == content_type
    assert response.json()["photos"][0].endswith("." + ext)


def test_type_is_judged_by_content_not_declared_type(client, host_listing, fake_s3):
    token, listing_id = host_listing("photo-gif@example.com")

    response = _upload(client, listing_id, token, GIF, filename="fake.jpg", content_type="image/jpeg")

    assert response.status_code == 415
    assert fake_s3.objects == {}


def test_photo_over_5mb_is_rejected(client, host_listing, fake_s3):
    token, listing_id = host_listing("photo-big@example.com")

    response = _upload(client, listing_id, token, JPEG + b"\x00" * (5 * 1024 * 1024))

    assert response.status_code == 413
    assert fake_s3.objects == {}


def test_only_the_owner_can_upload(client, host_listing, signup, fake_s3):
    _, listing_id = host_listing("photo-real-owner@example.com")
    other_host = signup("photo-other-host@example.com", role="host")["access_token"]
    renter = signup("photo-renter@example.com", role="renter")["access_token"]

    assert _upload(client, listing_id, other_host, JPEG).status_code == 403
    assert _upload(client, listing_id, renter, JPEG).status_code == 403
    assert client.post(f"/api/listings/{listing_id}/photos", files={"photo": ("a.jpg", JPEG, "image/jpeg")}).status_code == 401
    assert fake_s3.objects == {}


def test_listing_is_limited_to_8_photos(client, host_listing, fake_s3):
    token, listing_id = host_listing("photo-limit@example.com")

    for _ in range(8):
        assert _upload(client, listing_id, token, JPEG).status_code == 201
    response = _upload(client, listing_id, token, JPEG)

    assert response.status_code == 409
    assert len(fake_s3.objects) == 8
    assert len(client.get(f"/api/listings/{listing_id}").json()["photos"]) == 8


def test_unconfigured_storage_is_503(client, host_listing, monkeypatch):
    monkeypatch.setattr(settings, "s3_bucket", "")
    token, listing_id = host_listing("photo-unconfigured@example.com")

    assert _upload(client, listing_id, token, JPEG).status_code == 503


def test_missing_listing_is_404(client, signup, fake_s3):
    token = signup("photo-404@example.com", role="host")["access_token"]

    assert _upload(client, "does-not-exist", token, JPEG).status_code == 404
