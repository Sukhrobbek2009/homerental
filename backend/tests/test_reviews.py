from datetime import date, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app import models
from app.database import SessionLocal


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _create_listing(client, host_token: str, title: str = "Reviewed place") -> dict:
    response = client.post(
        "/api/listings",
        headers=_auth_header(host_token),
        json={
            "listing_type": "home",
            "title": title,
            "location": "Tashkent",
            "price": 100,
            "price_unit": "night",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _book(client, renter_token: str, listing_id: str, offset_days: int = 0) -> dict:
    start = date.today() + timedelta(days=30 + offset_days)
    response = client.post(
        "/api/bookings",
        headers=_auth_header(renter_token),
        json={
            "listing_id": listing_id,
            "start_date": start.isoformat(),
            "end_date": (start + timedelta(days=2)).isoformat(),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _complete(client, host_token: str, booking_id: str) -> None:
    response = client.patch(
        f"/api/bookings/{booking_id}/status",
        headers=_auth_header(host_token),
        json={"status": "completed"},
    )
    assert response.status_code == 200, response.text


def _review(client, renter_token: str, booking_id: str, rating: int = 5, comment: str = "Great stay"):
    return client.post(
        "/api/reviews",
        headers=_auth_header(renter_token),
        json={"booking_id": booking_id, "rating": rating, "comment": comment},
    )


@pytest.fixture()
def completed_stay(client, signup):
    """A host, a renter, a listing, and a completed booking — unique per test via `prefix`."""

    def _make(prefix: str) -> dict:
        host = signup(f"{prefix}-host@example.com", role="host")
        renter = signup(f"{prefix}-renter@example.com", role="renter")
        listing = _create_listing(client, host["access_token"])
        booking = _book(client, renter["access_token"], listing["id"])
        _complete(client, host["access_token"], booking["id"])
        return {"host": host, "renter": renter, "listing": listing, "booking": booking}

    return _make


# --- POST /reviews ---------------------------------------------------------


def test_renter_can_review_completed_booking(client, completed_stay):
    stay = completed_stay("rev-ok")
    response = _review(client, stay["renter"]["access_token"], stay["booking"]["id"], rating=4)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["listing_id"] == stay["listing"]["id"]
    assert body["author_id"] == stay["renter"]["user"]["id"]
    assert body["rating"] == 4


def test_cannot_review_booking_that_is_not_completed(client, signup):
    host = signup("rev-pending-host@example.com", role="host")
    renter = signup("rev-pending-renter@example.com", role="renter")
    listing = _create_listing(client, host["access_token"])
    booking = _book(client, renter["access_token"], listing["id"])

    response = _review(client, renter["access_token"], booking["id"])
    assert response.status_code == 400


def test_cannot_review_someone_elses_booking(client, signup, completed_stay):
    stay = completed_stay("rev-other")
    stranger = signup("rev-other-stranger@example.com", role="renter")

    response = _review(client, stranger["access_token"], stay["booking"]["id"])
    assert response.status_code == 404

    # The host can't review their own guest's booking either.
    response = _review(client, stay["host"]["access_token"], stay["booking"]["id"])
    assert response.status_code == 404


def test_second_review_for_same_booking_is_rejected(client, completed_stay):
    stay = completed_stay("rev-dup")
    token = stay["renter"]["access_token"]
    assert _review(client, token, stay["booking"]["id"]).status_code == 201
    assert _review(client, token, stay["booking"]["id"]).status_code == 409


def test_database_enforces_one_review_per_booking(client, completed_stay):
    """Even if the code-level check is bypassed (e.g. a race), the unique index holds."""
    stay = completed_stay("rev-unique")
    db = SessionLocal()
    try:
        for _ in range(2):
            db.add(
                models.Review(
                    booking_id=stay["booking"]["id"],
                    listing_id=stay["listing"]["id"],
                    author_id=stay["renter"]["user"]["id"],
                    rating=5,
                )
            )
        with pytest.raises(IntegrityError):
            db.commit()
    finally:
        db.rollback()
        db.close()


def test_racing_review_returns_409_not_500(client, completed_stay, monkeypatch):
    """Simulate losing a race: the pre-check sees no review, but one lands before commit."""
    stay = completed_stay("rev-race")

    db = SessionLocal()
    try:
        db.add(
            models.Review(
                booking_id=stay["booking"]["id"],
                listing_id=stay["listing"]["id"],
                author_id=stay["renter"]["user"]["id"],
                rating=5,
            )
        )
        db.commit()
    finally:
        db.close()

    original_first = __import__("sqlalchemy.orm", fromlist=["Query"]).Query.first

    def first_ignoring_existing_review(self):
        entity = self.column_descriptions[0]["entity"] if self.column_descriptions else None
        if entity is models.Review:
            return None
        return original_first(self)

    monkeypatch.setattr("sqlalchemy.orm.Query.first", first_ignoring_existing_review)

    response = _review(client, stay["renter"]["access_token"], stay["booking"]["id"])
    assert response.status_code == 409


@pytest.mark.parametrize("rating", [0, 6])
def test_rating_must_be_between_1_and_5(client, completed_stay, rating):
    stay = completed_stay(f"rev-range-{rating}")
    assert _review(client, stay["renter"]["access_token"], stay["booking"]["id"], rating=rating).status_code == 422


# --- POST /reviews/{id}/reply ----------------------------------------------


def test_only_listing_owner_can_reply_and_only_once(client, signup, completed_stay):
    stay = completed_stay("rev-reply")
    review_id = _review(client, stay["renter"]["access_token"], stay["booking"]["id"]).json()["id"]
    other_host = signup("rev-reply-other-host@example.com", role="host")

    for token in (stay["renter"]["access_token"], other_host["access_token"]):
        response = client.post(
            f"/api/reviews/{review_id}/reply", headers=_auth_header(token), json={"reply": "Thanks!"}
        )
        assert response.status_code == 403

    host_headers = _auth_header(stay["host"]["access_token"])
    first = client.post(f"/api/reviews/{review_id}/reply", headers=host_headers, json={"reply": "Thanks!"})
    assert first.status_code == 200
    assert first.json()["host_reply"] == "Thanks!"

    second = client.post(f"/api/reviews/{review_id}/reply", headers=host_headers, json={"reply": "Edited"})
    assert second.status_code == 409

    reviews = client.get(f"/api/reviews/listing/{stay['listing']['id']}").json()
    assert reviews[0]["host_reply"] == "Thanks!"


def test_reply_to_unknown_review_is_404(client, signup):
    host = signup("rev-reply-404-host@example.com", role="host")
    response = client.post(
        "/api/reviews/nope/reply", headers=_auth_header(host["access_token"]), json={"reply": "Hi"}
    )
    assert response.status_code == 404


# --- POST /reviews/{id}/report ---------------------------------------------


def test_report_flags_review_but_author_cannot_report_own(client, signup, completed_stay):
    stay = completed_stay("rev-report")
    review_id = _review(client, stay["renter"]["access_token"], stay["booking"]["id"]).json()["id"]

    own = client.post(f"/api/reviews/{review_id}/report", headers=_auth_header(stay["renter"]["access_token"]))
    assert own.status_code == 400

    reporter = signup("rev-report-reporter@example.com", role="renter")
    response = client.post(f"/api/reviews/{review_id}/report", headers=_auth_header(reporter["access_token"]))
    assert response.status_code == 200
    assert response.json()["flagged"] is True


def test_report_requires_authentication(client, completed_stay):
    stay = completed_stay("rev-report-anon")
    review_id = _review(client, stay["renter"]["access_token"], stay["booking"]["id"]).json()["id"]
    assert client.post(f"/api/reviews/{review_id}/report").status_code == 401


# --- Listing rating aggregates ---------------------------------------------


def _listing_from_index(client, listing_id: str) -> dict:
    listings = client.get("/api/listings").json()
    return next(item for item in listings if item["id"] == listing_id)


def test_listing_without_reviews_has_null_rating(client, signup):
    host = signup("rev-agg-new-host@example.com", role="host")
    listing = _create_listing(client, host["access_token"], title="Brand new")

    assert listing["rating_avg"] is None
    assert listing["review_count"] == 0

    detail = client.get(f"/api/listings/{listing['id']}").json()
    assert detail["rating_avg"] is None
    assert detail["review_count"] == 0

    indexed = _listing_from_index(client, listing["id"])
    assert indexed["rating_avg"] is None
    assert indexed["review_count"] == 0


def test_listing_rating_is_average_excluding_reported_reviews(client, signup):
    host = signup("rev-agg-host@example.com", role="host")
    listing = _create_listing(client, host["access_token"], title="Rated place")
    renters = [signup(f"rev-agg-renter{i}@example.com", role="renter") for i in range(3)]

    review_ids = []
    for i, (renter, rating) in enumerate(zip(renters, [5, 4, 1])):
        booking = _book(client, renter["access_token"], listing["id"], offset_days=i * 10)
        _complete(client, host["access_token"], booking["id"])
        response = _review(client, renter["access_token"], booking["id"], rating=rating)
        assert response.status_code == 201, response.text
        review_ids.append(response.json()["id"])

    detail = client.get(f"/api/listings/{listing['id']}").json()
    assert detail["review_count"] == 3
    assert detail["rating_avg"] == pytest.approx(3.33, abs=0.01)

    # Reporting the 1-star review removes it from the aggregate.
    reporter = signup("rev-agg-reporter@example.com", role="renter")
    client.post(f"/api/reviews/{review_ids[2]}/report", headers=_auth_header(reporter["access_token"]))

    detail = client.get(f"/api/listings/{listing['id']}").json()
    assert detail["review_count"] == 2
    assert detail["rating_avg"] == pytest.approx(4.5)

    indexed = _listing_from_index(client, listing["id"])
    assert indexed["review_count"] == 2
    assert indexed["rating_avg"] == pytest.approx(4.5)

    mine = client.get("/api/listings/mine", headers=_auth_header(host["access_token"])).json()
    assert next(item for item in mine if item["id"] == listing["id"])["rating_avg"] == pytest.approx(4.5)


def test_listing_with_only_reported_reviews_is_null_again(client, signup, completed_stay):
    stay = completed_stay("rev-agg-allreported")
    review_id = _review(client, stay["renter"]["access_token"], stay["booking"]["id"]).json()["id"]
    reporter = signup("rev-agg-allreported-reporter@example.com", role="renter")
    client.post(f"/api/reviews/{review_id}/report", headers=_auth_header(reporter["access_token"]))

    detail = client.get(f"/api/listings/{stay['listing']['id']}").json()
    assert detail["rating_avg"] is None
    assert detail["review_count"] == 0
