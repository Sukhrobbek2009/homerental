from datetime import date, timedelta

import pytest

from app import models
from app.database import SessionLocal


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _listing_body(**overrides) -> dict:
    body = {"listing_type": "home", "title": "Test home", "location": "Austin, TX", "price": 100, "price_unit": "night"}
    body.update(overrides)
    return body


@pytest.fixture()
def host(signup):
    def _host(email: str) -> str:
        return signup(email, role="host")["access_token"]

    return _host


@pytest.fixture()
def create_listing(client):
    def _create(token: str, **overrides) -> dict:
        response = client.post("/api/listings", json=_listing_body(**overrides), headers=_auth(token))
        assert response.status_code == 201, response.text
        return response.json()

    return _create


def _set_listing_fields(listing_id: str, **fields) -> None:
    db = SessionLocal()
    try:
        listing = db.get(models.Listing, listing_id)
        for field, value in fields.items():
            setattr(listing, field, value)
        db.commit()
    finally:
        db.close()


def _add_review(listing_id: str, author_id: str, rating: int) -> None:
    db = SessionLocal()
    try:
        listing = db.get(models.Listing, listing_id)
        booking = models.Booking(
            listing_id=listing_id,
            renter_id=author_id,
            host_id=listing.host_id,
            start_date=date(2020, 1, 1),
            end_date=date(2020, 1, 3),
            total_price=listing.price * 2,
            status=models.BookingStatus.completed,
        )
        db.add(booking)
        db.flush()
        db.add(models.Review(booking_id=booking.id, listing_id=listing_id, author_id=author_id, rating=rating))
        db.commit()
    finally:
        db.close()


def test_create_takes_owner_from_token_not_body(client, host, signup):
    token = host("create-owner@example.com")
    other = signup("create-other@example.com", role="host")

    response = client.post(
        "/api/listings",
        json=_listing_body(host_id=other["user"]["id"], owner_id=other["user"]["id"]),
        headers=_auth(token),
    )

    assert response.status_code == 201, response.text
    me = client.get("/api/auth/me", headers=_auth(token)).json()
    assert response.json()["host_id"] == me["id"] != other["user"]["id"]


def test_create_requires_host(client, signup):
    renter = signup("create-renter@example.com")["access_token"]

    assert client.post("/api/listings", json=_listing_body(), headers=_auth(renter)).status_code == 403
    assert client.post("/api/listings", json=_listing_body()).status_code == 401


@pytest.mark.parametrize(
    "overrides",
    [
        {"price": 0},
        {"price": -5},
        {"title": "ab"},
        {"listing_type": "boat"},
        {"price_unit": "week"},
        {"location": ""},
    ],
)
def test_create_rejects_invalid_input(client, host, overrides):
    token = host(f"create-invalid-{len(str(overrides))}-{list(overrides)[0]}@example.com")

    response = client.post("/api/listings", json=_listing_body(**overrides), headers=_auth(token))

    assert response.status_code == 422


def test_get_listing_by_id(client, host, create_listing):
    listing = create_listing(host("get-one@example.com"), title="Lake cabin")

    response = client.get(f"/api/listings/{listing['id']}")

    assert response.status_code == 200
    assert response.json()["title"] == "Lake cabin"
    assert client.get("/api/listings/does-not-exist").status_code == 404


def test_list_filters(client, host, create_listing):
    token = host("filters@example.com")
    city = "Filterville"
    cheap_home = create_listing(token, location=f"{city}, OR", price=50)
    pricey_home = create_listing(token, location=f"{city}, OR", price=500)
    car = create_listing(token, location=f"{city}, OR", price=80, listing_type="car", price_unit="day")
    paused = create_listing(token, location=f"{city}, OR", price=90)
    _set_listing_fields(pricey_home["id"], verified=True)
    _set_listing_fields(paused["id"], status=models.ListingStatus.paused)

    def ids(**params) -> set[str]:
        response = client.get("/api/listings", params={"city": city.lower(), **params})
        assert response.status_code == 200, response.text
        return {item["id"] for item in response.json()}

    assert ids() == {cheap_home["id"], pricey_home["id"], car["id"]}
    assert ids(type="car") == {car["id"]}
    assert ids(min_price=60, max_price=100) == {car["id"]}
    assert ids(verified_only=True) == {pricey_home["id"]}


def test_list_rejects_bad_query_params(client):
    assert client.get("/api/listings", params={"type": "boat"}).status_code == 422
    assert client.get("/api/listings", params={"min_price": -1}).status_code == 422
    assert client.get("/api/listings", params={"sort": "newest"}).status_code == 422
    assert client.get("/api/listings", params={"page": 0}).status_code == 422
    assert client.get("/api/listings", params={"page_size": 101}).status_code == 422


def test_sort_by_price_and_top_rated(client, host, signup, create_listing):
    token = host("sorting@example.com")
    reviewer = signup("sorting-reviewer@example.com")["user"]["id"]
    city = "Sortburg"
    unrated = create_listing(token, location=city, price=300)
    good = create_listing(token, location=city, price=200)
    best = create_listing(token, location=city, price=100)
    _add_review(good["id"], reviewer, 3)
    _add_review(best["id"], reviewer, 5)

    by_price = client.get("/api/listings", params={"city": city, "sort": "price"}).json()
    top_rated = client.get("/api/listings", params={"city": city, "sort": "top_rated"}).json()

    assert [item["id"] for item in by_price] == [best["id"], good["id"], unrated["id"]]
    assert [item["id"] for item in top_rated] == [best["id"], good["id"], unrated["id"]]


def test_pagination(client, host, create_listing):
    token = host("paging@example.com")
    city = "Pagetown"
    created = [create_listing(token, location=city, price=10 + i) for i in range(5)]

    first = client.get("/api/listings", params={"city": city, "sort": "price", "page": 1, "page_size": 2})
    last = client.get("/api/listings", params={"city": city, "sort": "price", "page": 3, "page_size": 2})

    assert first.headers["X-Total-Count"] == "5"
    assert [item["id"] for item in first.json()] == [created[0]["id"], created[1]["id"]]
    assert [item["id"] for item in last.json()] == [created[4]["id"]]


@pytest.mark.parametrize("method", ["put", "patch"])
def test_owner_can_update(client, host, create_listing, method):
    token = host(f"update-owner-{method}@example.com")
    listing = create_listing(token)

    response = getattr(client, method)(
        f"/api/listings/{listing['id']}", json={"title": "Renamed", "price": 150}, headers=_auth(token)
    )

    assert response.status_code == 200, response.text
    assert response.json()["title"] == "Renamed"
    assert response.json()["price"] == 150


@pytest.mark.parametrize("method", ["put", "patch"])
def test_non_owner_cannot_update(client, host, signup, create_listing, method):
    listing = create_listing(host(f"update-real-{method}@example.com"))
    other_host = host(f"update-other-{method}@example.com")
    renter = signup(f"update-renter-{method}@example.com")["access_token"]

    for token in (other_host, renter):
        response = getattr(client, method)(
            f"/api/listings/{listing['id']}", json={"title": "Hijacked"}, headers=_auth(token)
        )
        assert response.status_code == 403

    assert client.get(f"/api/listings/{listing['id']}").json()["title"] == "Test home"


def test_update_rejects_invalid_input(client, host, create_listing):
    token = host("update-invalid@example.com")
    listing = create_listing(token)

    response = client.put(f"/api/listings/{listing['id']}", json={"price": -1}, headers=_auth(token))

    assert response.status_code == 422


def test_non_owner_cannot_delete(client, host, create_listing):
    listing = create_listing(host("delete-real@example.com"))
    other = host("delete-other@example.com")

    response = client.delete(f"/api/listings/{listing['id']}", headers=_auth(other))

    assert response.status_code == 403
    assert client.get(f"/api/listings/{listing['id']}").status_code == 200


def test_delete_without_bookings_removes_listing(client, host, create_listing):
    token = host("delete-clean@example.com")
    listing = create_listing(token)

    response = client.delete(f"/api/listings/{listing['id']}", headers=_auth(token))

    assert response.status_code == 200
    assert response.json()["deleted"] is True
    assert client.get(f"/api/listings/{listing['id']}").status_code == 404


def test_delete_with_bookings_marks_unavailable(client, host, signup, create_listing):
    token = host("delete-booked@example.com")
    listing = create_listing(token, location="Bookedville")
    renter = signup("delete-booked-renter@example.com")["access_token"]
    start = date.today() + timedelta(days=10)
    booking = client.post(
        "/api/bookings",
        json={"listing_id": listing["id"], "start_date": str(start), "end_date": str(start + timedelta(days=2))},
        headers=_auth(renter),
    )
    assert booking.status_code == 201, booking.text

    response = client.delete(f"/api/listings/{listing['id']}", headers=_auth(token))

    assert response.status_code == 200
    body = response.json()
    assert body["deleted"] is False
    assert body["listing"]["status"] == "paused"
    assert client.get(f"/api/listings/{listing['id']}").status_code == 200
    assert client.get("/api/listings", params={"city": "Bookedville"}).json() == []
