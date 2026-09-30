"""Double-booking protection on Postgres.

These tests need a real Postgres server, because the protection they check is a
Postgres exclusion constraint. Set TEST_POSTGRES_URL to any database on a
server where the user may CREATE DATABASE, e.g.

    TEST_POSTGRES_URL=postgresql://postgres@127.0.0.1:5432/postgres pytest

A temporary database is created for the run, migrated with Alembic, and dropped
afterwards; the database named in the URL is never modified. Without the
variable, these tests are skipped.
"""

import os
import threading
import uuid
from datetime import date, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app import models
from app.config import settings
from app.database import get_db
from app.main import app
from app.routers.bookings import DATES_TAKEN_MESSAGE

POSTGRES_URL = os.environ.get("TEST_POSTGRES_URL")

pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="TEST_POSTGRES_URL is not set")


@pytest.fixture(scope="module")
def pg_sessions():
    from alembic import command
    from alembic.config import Config

    server_url = make_url(POSTGRES_URL)
    db_name = f"homerental_test_{uuid.uuid4().hex[:12]}"
    admin_engine = create_engine(server_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{db_name}"'))

    test_url = server_url.set(database=db_name).render_as_string(hide_password=False)
    alembic_cfg = Config()
    alembic_cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
    original_url = settings.database_url
    settings.database_url = test_url  # alembic/env.py migrates whatever this points at
    try:
        command.upgrade(alembic_cfg, "head")
    finally:
        settings.database_url = original_url

    engine = create_engine(test_url)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    def _get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db
    try:
        yield Session
    finally:
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()
        with admin_engine.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)'))
        admin_engine.dispose()


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _days(n: int) -> date:
    return date.today() + timedelta(days=n)


@pytest.fixture()
def booked_listing(client, signup, pg_sessions):
    def _make(prefix: str) -> tuple[str, dict]:
        host = signup(f"{prefix}-host@example.com", role="host")["access_token"]
        renter = signup(f"{prefix}-renter@example.com")["access_token"]
        response = client.post(
            "/api/listings",
            json={"listing_type": "home", "title": "Race home", "location": "Austin, TX", "price": 100, "price_unit": "night"},
            headers=_auth(host),
        )
        assert response.status_code == 201, response.text
        return renter, response.json()

    return _make


def _active_bookings(Session, listing_id: str) -> list[models.Booking]:
    with Session() as db:
        return (
            db.query(models.Booking)
            .filter(models.Booking.listing_id == listing_id, models.Booking.status != models.BookingStatus.cancelled)
            .all()
        )


def test_simultaneous_identical_requests_book_exactly_once(client, booked_listing, pg_sessions):
    renter, listing = booked_listing("race")
    rounds = 10

    for i in range(rounds):
        body = {"listing_id": listing["id"], "start_date": str(_days(10 + 3 * i)), "end_date": str(_days(12 + 3 * i))}
        start_together = threading.Barrier(2)
        responses = [None, None]

        def fire(slot: int) -> None:
            start_together.wait()
            responses[slot] = client.post("/api/bookings", json=body, headers=_auth(renter))

        threads = [threading.Thread(target=fire, args=(slot,)) for slot in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        codes = sorted(r.status_code for r in responses)
        assert codes == [201, 409], [r.text for r in responses]
        loser = next(r for r in responses if r.status_code == 409)
        assert loser.json()["detail"] == DATES_TAKEN_MESSAGE

    assert len(_active_bookings(pg_sessions, listing["id"])) == rounds


def test_constraint_violation_is_returned_as_409(client, booked_listing, pg_sessions):
    """A conflict only the database can see still comes back as a clean 409."""
    renter, listing = booked_listing("constraint-409")
    # The endpoint's own pre-check only looks at pending/confirmed bookings, so an
    # overlapping 'completed' booking gets past it and is caught by the constraint.
    with pg_sessions() as db:
        db.add(models.Booking(
            listing_id=listing["id"], renter_id=listing["host_id"], host_id=listing["host_id"],
            start_date=_days(40), end_date=_days(43), total_price=300, status=models.BookingStatus.completed,
        ))
        db.commit()

    response = client.post(
        "/api/bookings",
        json={"listing_id": listing["id"], "start_date": str(_days(41)), "end_date": str(_days(44))},
        headers=_auth(renter),
    )

    assert response.status_code == 409, response.text
    assert response.json()["detail"] == DATES_TAKEN_MESSAGE


def test_constraint_rules(booked_listing, pg_sessions):
    _, listing = booked_listing("constraint-rules")

    def insert(start: int, end: int, status=models.BookingStatus.confirmed) -> None:
        with pg_sessions() as db:
            db.add(models.Booking(
                listing_id=listing["id"], renter_id=listing["host_id"], host_id=listing["host_id"],
                start_date=_days(start), end_date=_days(end), total_price=100, status=status,
            ))
            db.commit()

    insert(10, 13)
    with pytest.raises(IntegrityError) as overlap:
        insert(12, 15)
    orig = overlap.value.orig
    assert (getattr(orig, "pgcode", None) or getattr(orig, "sqlstate", None)) == "23P01"

    insert(13, 15)  # checkout day of one stay can be the check-in day of the next
    insert(10, 13, status=models.BookingStatus.cancelled)  # cancelled bookings don't hold dates
    with pytest.raises(IntegrityError):
        insert(11, 12, status=models.BookingStatus.pending)
