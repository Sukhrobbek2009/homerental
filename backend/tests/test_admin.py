import re
from datetime import date, timedelta

import pytest
from fastapi.routing import APIRoute

from app.routers import admin

# The endpoints the admin API is specified to expose. Kept explicit so a
# renamed or dropped route fails loudly instead of silently shrinking coverage.
SPEC_ADMIN_ROUTES = {
    ("GET", "/api/admin/verification-requests"),
    ("POST", "/api/admin/hosts/{user_id}/verify"),
    ("POST", "/api/admin/hosts/{user_id}/reject"),
    ("GET", "/api/admin/reported-reviews"),
    ("POST", "/api/admin/reviews/{review_id}/clear"),
    ("POST", "/api/admin/reviews/{review_id}/remove"),
    ("POST", "/api/admin/bookings/{booking_id}/complete"),
}


def _registered_admin_routes() -> list[tuple[str, str]]:
    """Every route actually mounted under /api/admin, so new routes are covered automatically."""
    routes = set()
    for route in admin.router.routes:
        if isinstance(route, APIRoute):
            for method in route.methods:
                routes.add((method, route.path))
    return sorted(routes)


ADMIN_ROUTES = _registered_admin_routes()


def _concrete(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "dummy-id", path)


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _slug(method: str, path: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (method + path).lower()).strip("-")


def test_every_spec_admin_route_is_registered():
    assert SPEC_ADMIN_ROUTES <= set(ADMIN_ROUTES)


@pytest.mark.parametrize("method,path", ADMIN_ROUTES)
def test_renter_is_forbidden_from_every_admin_route(client, signup, method, path):
    tokens = signup(f"renter-{_slug(method, path)}@example.com", role="renter")
    response = client.request(method, _concrete(path), headers=_auth_header(tokens["access_token"]))
    assert response.status_code == 403


@pytest.mark.parametrize("method,path", ADMIN_ROUTES)
def test_host_is_forbidden_from_every_admin_route(client, signup, method, path):
    tokens = signup(f"host-{_slug(method, path)}@example.com", role="host")
    response = client.request(method, _concrete(path), headers=_auth_header(tokens["access_token"]))
    assert response.status_code == 403


@pytest.mark.parametrize("method,path", ADMIN_ROUTES)
def test_anonymous_is_unauthorized_on_every_admin_route(client, method, path):
    assert client.request(method, _concrete(path)).status_code == 401


def test_forbidden_request_has_no_side_effects(client, signup):
    """A 403 must be decided before the handler runs, not after it has written."""
    host = signup("admin-noeffect-host@example.com", role="host")
    renter = signup("admin-noeffect-renter@example.com", role="renter")
    listing = client.post(
        "/api/listings",
        headers=_auth_header(host["access_token"]),
        json={"listing_type": "home", "title": "Guarded", "location": "Tashkent", "price": 50, "price_unit": "night"},
    ).json()
    start = date.today() + timedelta(days=40)
    booking = client.post(
        "/api/bookings",
        headers=_auth_header(renter["access_token"]),
        json={"listing_id": listing["id"], "start_date": start.isoformat(), "end_date": (start + timedelta(days=1)).isoformat()},
    ).json()

    response = client.post(
        f"/api/admin/bookings/{booking['id']}/complete", headers=_auth_header(renter["access_token"])
    )
    assert response.status_code == 403

    mine = client.get("/api/bookings/mine", headers=_auth_header(renter["access_token"])).json()
    assert next(b for b in mine if b["id"] == booking["id"])["status"] != "completed"


def test_admin_can_use_admin_routes(client, make_admin):
    token = make_admin("admin-smoke-check@example.com")
    for path in ("/api/admin/verification-requests", "/api/admin/reported-reviews"):
        response = client.get(path, headers=_auth_header(token))
        assert response.status_code == 200, path
