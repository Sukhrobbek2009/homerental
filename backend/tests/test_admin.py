import pytest

ADMIN_ROUTES = [
    ("GET", "/api/admin/verification-requests"),
    ("POST", "/api/admin/verification-requests/dummy-id/approve"),
    ("POST", "/api/admin/verification-requests/dummy-id/reject"),
    ("GET", "/api/admin/reviews/flagged"),
    ("POST", "/api/admin/reviews/dummy-id/clear"),
    ("DELETE", "/api/admin/reviews/dummy-id"),
    ("POST", "/api/admin/bookings/dummy-id/complete"),
]


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _slug(method: str, path: str) -> str:
    return (method + path).lower().replace("/", "-")


@pytest.mark.parametrize("method,path", ADMIN_ROUTES)
def test_renter_is_forbidden_from_every_admin_route(client, signup, method, path):
    tokens = signup(f"renter-{_slug(method, path)}@example.com", role="renter")
    response = client.request(method, path, headers=_auth_header(tokens["access_token"]))
    assert response.status_code == 403


@pytest.mark.parametrize("method,path", ADMIN_ROUTES)
def test_host_is_forbidden_from_every_admin_route(client, signup, method, path):
    tokens = signup(f"host-{_slug(method, path)}@example.com", role="host")
    response = client.request(method, path, headers=_auth_header(tokens["access_token"]))
    assert response.status_code == 403


def test_admin_can_use_admin_routes(client, make_admin):
    token = make_admin("admin-smoke-check@example.com")
    response = client.get("/api/admin/verification-requests", headers=_auth_header(token))
    assert response.status_code == 200
