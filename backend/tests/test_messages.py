def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_third_user_cannot_read_others_thread(client, signup):
    host = signup("host-msg@example.com", role="host")
    renter = signup("renter-msg@example.com", role="renter")
    outsider = signup("outsider-msg@example.com", role="renter")

    listing = client.post(
        "/api/listings",
        headers=_auth_header(host["access_token"]),
        json={
            "listing_type": "home",
            "title": "Cozy cabin",
            "location": "Denver, CO",
            "price": 100,
            "price_unit": "night",
        },
    ).json()

    message = client.post(
        "/api/messages",
        headers=_auth_header(renter["access_token"]),
        json={"listing_id": listing["id"], "body": "Is this available next week?"},
    ).json()
    thread_id = message["thread_id"]

    # Both real participants can read the thread.
    as_host = client.get(f"/api/messages/threads/{thread_id}", headers=_auth_header(host["access_token"]))
    assert as_host.status_code == 200
    as_renter = client.get(f"/api/messages/threads/{thread_id}", headers=_auth_header(renter["access_token"]))
    assert as_renter.status_code == 200

    # An unrelated third user cannot read it...
    as_outsider = client.get(f"/api/messages/threads/{thread_id}", headers=_auth_header(outsider["access_token"]))
    assert as_outsider.status_code == 403

    # ...and cannot reply into it either.
    reply_attempt = client.post(
        f"/api/messages/threads/{thread_id}/reply",
        headers=_auth_header(outsider["access_token"]),
        json={"body": "sneaking in"},
    )
    assert reply_attempt.status_code == 403


def test_unknown_thread_is_404_not_403(client, signup):
    renter = signup("renter-unknown-thread@example.com", role="renter")
    response = client.get(
        "/api/messages/threads/does-not-exist", headers=_auth_header(renter["access_token"])
    )
    assert response.status_code == 404


def test_empty_message_is_rejected(client, signup):
    host = signup("host-empty-msg@example.com", role="host")
    renter = signup("renter-empty-msg@example.com", role="renter")

    listing = client.post(
        "/api/listings",
        headers=_auth_header(host["access_token"]),
        json={
            "listing_type": "home",
            "title": "Quiet studio",
            "location": "Austin, TX",
            "price": 80,
            "price_unit": "night",
        },
    ).json()

    response = client.post(
        "/api/messages",
        headers=_auth_header(renter["access_token"]),
        json={"listing_id": listing["id"], "body": "   "},
    )
    assert response.status_code == 422


def test_message_body_is_capped_at_2000_chars(client, signup):
    host = signup("host-long-msg@example.com", role="host")
    renter = signup("renter-long-msg@example.com", role="renter")

    listing = client.post(
        "/api/listings",
        headers=_auth_header(host["access_token"]),
        json={
            "listing_type": "home",
            "title": "Loft with a view",
            "location": "Chicago, IL",
            "price": 150,
            "price_unit": "night",
        },
    ).json()

    response = client.post(
        "/api/messages",
        headers=_auth_header(renter["access_token"]),
        json={"listing_id": listing["id"], "body": "x" * 3000},
    )
    assert response.status_code == 201
    assert len(response.json()["body"]) == 2000
