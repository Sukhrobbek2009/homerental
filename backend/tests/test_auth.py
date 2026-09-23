def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _tamper(token: str) -> str:
    mid = len(token) // 2
    flipped = "a" if token[mid] != "a" else "b"
    return token[:mid] + flipped + token[mid + 1 :]


def test_me_without_token_is_401(client):
    response = client.get("/api/auth/me")
    assert response.status_code == 401


def test_me_with_tampered_token_is_401(client, signup):
    tokens = signup("tamper-me@example.com")
    response = client.get("/api/auth/me", headers=_auth_header(_tamper(tokens["access_token"])))
    assert response.status_code == 401


def test_me_with_valid_token_returns_current_user(client, signup):
    tokens = signup("me-check@example.com")
    response = client.get("/api/auth/me", headers=_auth_header(tokens["access_token"]))
    assert response.status_code == 200
    assert response.json()["email"] == "me-check@example.com"


def test_renter_hitting_host_only_route_is_403(client, signup):
    tokens = signup("renter-only@example.com", role="renter")
    response = client.get("/api/_test/host-only", headers=_auth_header(tokens["access_token"]))
    assert response.status_code == 403


def test_host_hitting_host_only_route_is_200(client, signup):
    tokens = signup("host-ok@example.com", role="host")
    response = client.get("/api/_test/host-only", headers=_auth_header(tokens["access_token"]))
    assert response.status_code == 200


def test_renter_hitting_admin_only_route_is_403(client, signup):
    tokens = signup("renter-admin-check@example.com", role="renter")
    response = client.get("/api/admin/verification-requests", headers=_auth_header(tokens["access_token"]))
    assert response.status_code == 403


def test_admin_hitting_admin_only_route_is_200(client, make_admin):
    token = make_admin()
    response = client.get("/api/admin/verification-requests", headers=_auth_header(token))
    assert response.status_code == 200
