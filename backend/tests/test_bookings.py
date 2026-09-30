from datetime import date, timedelta

import pytest


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _days(n: int) -> str:
    return str(date.today() + timedelta(days=n))


@pytest.fixture()
def listing(client, signup):
    def _make(prefix: str, **overrides) -> tuple[str, dict]:
        host_token = signup(f"{prefix}-host@example.com", role="host")["access_token"]
        body = {"listing_type": "home", "title": "Booking home", "location": "Austin, TX", "price": 120, "price_unit": "night"}
        body.update(overrides)
        response = client.post("/api/listings", json=body, headers=_auth(host_token))
        assert response.status_code == 201, response.text
        return host_token, response.json()

    return _make


def _book(client, token: str, listing_id: str, start: int, end: int, **extra):
    return client.post(
        "/api/bookings",
        json={"listing_id": listing_id, "start_date": _days(start), "end_date": _days(end), **extra},
        headers=_auth(token),
    )


def test_renter_books_and_price_is_computed_on_server(client, signup, listing):
    _, home = listing("price")
    renter = signup("price-renter@example.com")["access_token"]

    response = _book(client, renter, home["id"], 10, 13, total_price=1, price=1)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["total_price"] == 360
    assert body["status"] == "confirmed"


def test_only_renters_can_book(client, signup, listing):
    host_token, home = listing("role")
    other_host = signup("role-other-host@example.com", role="host")["access_token"]

    assert _book(client, host_token, home["id"], 10, 12).status_code == 403
    assert _book(client, other_host, home["id"], 10, 12).status_code == 403
    assert client.post("/api/bookings", json={"listing_id": home["id"], "start_date": _days(10), "end_date": _days(12)}).status_code == 401


def test_dates_must_be_inside_available_window(client, signup, listing):
    _, home = listing("window", available_from=_days(10), available_to=_days(20))
    renter = signup("window-renter@example.com")["access_token"]

    assert _book(client, renter, home["id"], 5, 12).status_code == 400
    assert _book(client, renter, home["id"], 18, 25).status_code == 400
    assert _book(client, renter, home["id"], 10, 20).status_code == 201


def test_end_must_be_after_start(client, signup, listing):
    _, home = listing("order")
    renter = signup("order-renter@example.com")["access_token"]

    assert _book(client, renter, home["id"], 12, 12).status_code == 422
    assert _book(client, renter, home["id"], 12, 10).status_code == 422


def test_overlapping_dates_are_rejected(client, signup, listing):
    _, home = listing("overlap")
    first = signup("overlap-first@example.com")["access_token"]
    second = signup("overlap-second@example.com")["access_token"]

    assert _book(client, first, home["id"], 10, 14).status_code == 201
    assert _book(client, second, home["id"], 12, 16).status_code == 409
    assert _book(client, second, home["id"], 14, 16).status_code == 201


def test_mine_and_host_lists(client, signup, listing):
    host_token, home = listing("lists")
    renter = signup("lists-renter@example.com")["access_token"]
    outsider = signup("lists-outsider@example.com")["access_token"]
    booking_id = _book(client, renter, home["id"], 10, 12).json()["id"]

    mine = client.get("/api/bookings/mine", headers=_auth(renter)).json()
    hosted = client.get("/api/bookings/host", headers=_auth(host_token)).json()

    assert [b["id"] for b in mine] == [booking_id]
    assert [b["id"] for b in hosted] == [booking_id]
    assert client.get("/api/bookings/mine", headers=_auth(outsider)).json() == []


@pytest.mark.parametrize("who", ["renter", "host"])
def test_renter_or_host_can_cancel(client, signup, listing, who):
    host_token, home = listing(f"cancel-{who}")
    renter = signup(f"cancel-{who}-renter@example.com")["access_token"]
    booking_id = _book(client, renter, home["id"], 10, 12).json()["id"]
    token = renter if who == "renter" else host_token

    response = client.post(f"/api/bookings/{booking_id}/cancel", headers=_auth(token))

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "cancelled"
    assert client.post(f"/api/bookings/{booking_id}/cancel", headers=_auth(token)).status_code == 400


def test_others_cannot_cancel(client, signup, listing):
    _, home = listing("cancel-outsider")
    renter = signup("cancel-outsider-renter@example.com")["access_token"]
    outsider = signup("cancel-outsider-other@example.com")["access_token"]
    booking_id = _book(client, renter, home["id"], 10, 12).json()["id"]

    assert client.post(f"/api/bookings/{booking_id}/cancel", headers=_auth(outsider)).status_code == 403
    assert client.post("/api/bookings/no-such-booking/cancel", headers=_auth(outsider)).status_code == 404


def test_cancelled_dates_can_be_rebooked(client, signup, listing):
    _, home = listing("rebook")
    first = signup("rebook-first@example.com")["access_token"]
    second = signup("rebook-second@example.com")["access_token"]
    booking_id = _book(client, first, home["id"], 10, 12).json()["id"]
    client.post(f"/api/bookings/{booking_id}/cancel", headers=_auth(first))

    assert _book(client, second, home["id"], 10, 12).status_code == 201
