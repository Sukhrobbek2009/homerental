import pytest



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


def test_signup_returns_tokens_and_user(client):
    response = client.post(
        "/api/auth/signup",
        json={"full_name": "New Person", "email": "New.Person@Example.com", "password": "password1", "role": "host"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["access_token"] and body["refresh_token"]
    assert body["user"]["email"] == "new.person@example.com"
    assert body["user"]["role"] == "host"
    assert "password" not in response.text and "password_hash" not in body["user"]


def test_signup_duplicate_email_is_409_case_insensitive(client, signup):
    signup("dupe@example.com")
    response = client.post(
        "/api/auth/signup",
        json={"full_name": "Dupe Again", "email": "DUPE@example.com", "password": "password1"},
    )
    assert response.status_code == 409


@pytest.mark.parametrize(
    "overrides",
    [{"password": "short1"}, {"password": "lettersonly"}, {"password": "12345678"}, {"email": "not-an-email"}, {"full_name": "A"}],
)
def test_signup_rejects_invalid_input(client, overrides):
    body = {"full_name": "Valid Name", "email": "valid-input@example.com", "password": "password1", **overrides}
    assert client.post("/api/auth/signup", json=body).status_code == 422


def test_signup_cannot_self_assign_admin(client):
    response = client.post(
        "/api/auth/signup",
        json={"full_name": "Sneaky", "email": "sneaky-signup@example.com", "password": "password1", "role": "admin"},
    )
    assert response.status_code == 422


def test_login_succeeds_with_correct_password(client, signup):
    signup("login-ok@example.com", password="password1")
    response = client.post("/api/auth/login", json={"email": "LOGIN-OK@example.com", "password": "password1"})
    assert response.status_code == 200
    token = response.json()["access_token"]
    assert client.get("/api/auth/me", headers=_auth_header(token)).json()["email"] == "login-ok@example.com"


def test_login_wrong_password_and_unknown_email_look_the_same(client, signup):
    signup("login-bad@example.com", password="password1")
    wrong = client.post("/api/auth/login", json={"email": "login-bad@example.com", "password": "password2"})
    unknown = client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "password1"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_refresh_token_cannot_be_used_as_access_token(client, signup):
    tokens = signup("refresh-misuse@example.com")
    assert client.get("/api/auth/me", headers=_auth_header(tokens["refresh_token"])).status_code == 401
    refreshed = client.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert refreshed.status_code == 200
    assert client.post("/api/auth/refresh", json={"refresh_token": tokens["access_token"]}).status_code == 401


def test_renter_can_become_host(client, renter):
    response = client.patch("/api/auth/me/role", json={"role": "host"}, headers=renter["headers"])
    assert response.status_code == 200
    assert response.json()["role"] == "host"


@pytest.mark.parametrize("who", ["renter", "host"])
def test_user_cannot_promote_themselves_to_admin(client, request, who):
    user = request.getfixturevalue(who)
    response = client.patch("/api/auth/me/role", json={"role": "admin"}, headers=user["headers"])
    assert response.status_code in (403, 422)
    assert client.get("/api/auth/me", headers=user["headers"]).json()["role"] == who
    assert client.get("/api/admin/verification-requests", headers=user["headers"]).status_code == 403
