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


def _create_listing(client, host_token: str, title: str = "Test listing") -> dict:
    response = client.post(
        "/api/listings",
        headers=_auth_header(host_token),
        json={
            "listing_type": "home",
            "title": title,
            "location": "Denver, CO",
            "price": 100,
            "price_unit": "night",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_message_goes_to_listing_owner(client, signup):
    host = signup("host-owner-lookup@example.com", role="host")
    renter = signup("renter-owner-lookup@example.com", role="renter")
    listing = _create_listing(client, host["access_token"])

    response = client.post(
        "/api/messages",
        headers=_auth_header(renter["access_token"]),
        json={"listing_id": listing["id"], "body": "Hello"},
    )
    assert response.status_code == 201
    assert response.json()["to_id"] == listing["host_id"]
    assert response.json()["from_id"] == renter["user"]["id"]


def test_cannot_message_unknown_or_own_listing(client, signup):
    host = signup("host-own-listing@example.com", role="host")
    listing = _create_listing(client, host["access_token"])

    own = client.post(
        "/api/messages",
        headers=_auth_header(host["access_token"]),
        json={"listing_id": listing["id"], "body": "Talking to myself"},
    )
    assert own.status_code == 400

    unknown = client.post(
        "/api/messages",
        headers=_auth_header(host["access_token"]),
        json={"listing_id": "no-such-listing", "body": "Hello?"},
    )
    assert unknown.status_code == 404


def test_outsider_does_not_see_thread_in_list_and_cannot_mark_it_read(client, signup):
    host = signup("host-outsider-list@example.com", role="host")
    renter = signup("renter-outsider-list@example.com", role="renter")
    outsider = signup("outsider-outsider-list@example.com", role="renter")
    listing = _create_listing(client, host["access_token"])

    thread_id = client.post(
        "/api/messages",
        headers=_auth_header(renter["access_token"]),
        json={"listing_id": listing["id"], "body": "Private question"},
    ).json()["thread_id"]

    outsider_threads = client.get("/api/messages/threads", headers=_auth_header(outsider["access_token"]))
    assert outsider_threads.status_code == 200
    assert outsider_threads.json() == []

    # A rejected read must not have side effects on the real recipient's unread state.
    as_outsider = client.get(f"/api/messages/threads/{thread_id}", headers=_auth_header(outsider["access_token"]))
    assert as_outsider.status_code == 403
    assert "messages" not in as_outsider.json()

    host_threads = client.get("/api/messages/threads", headers=_auth_header(host["access_token"])).json()
    assert [t["thread_id"] for t in host_threads] == [thread_id]
    assert host_threads[0]["unread_count"] == 1


def test_threads_are_newest_first_with_unread_counts_and_reading_marks_read(client, signup):
    host = signup("host-thread-order@example.com", role="host")
    renter = signup("renter-thread-order@example.com", role="renter")
    older = _create_listing(client, host["access_token"], title="Older thread")
    newer = _create_listing(client, host["access_token"], title="Newer thread")

    renter_headers = _auth_header(renter["access_token"])
    host_headers = _auth_header(host["access_token"])

    older_thread = client.post(
        "/api/messages", headers=renter_headers, json={"listing_id": older["id"], "body": "first"}
    ).json()["thread_id"]
    client.post("/api/messages", headers=renter_headers, json={"listing_id": older["id"], "body": "second"})
    newer_thread = client.post(
        "/api/messages", headers=renter_headers, json={"listing_id": newer["id"], "body": "third"}
    ).json()["thread_id"]

    threads = client.get("/api/messages/threads", headers=host_headers).json()
    assert [t["thread_id"] for t in threads] == [newer_thread, older_thread]
    assert [t["unread_count"] for t in threads] == [1, 2]
    assert threads[0]["last_message"] == "third"

    # The sender has nothing unread in their own messages.
    renter_threads = client.get("/api/messages/threads", headers=renter_headers).json()
    assert all(t["unread_count"] == 0 for t in renter_threads)

    detail = client.get(f"/api/messages/threads/{older_thread}", headers=host_headers).json()
    assert [m["body"] for m in detail["messages"]] == ["first", "second"]
    assert all(m["read"] for m in detail["messages"])

    threads = client.get("/api/messages/threads", headers=host_headers).json()
    unread_by_thread = {t["thread_id"]: t["unread_count"] for t in threads}
    assert unread_by_thread == {newer_thread: 1, older_thread: 0}

    # A reply bumps its thread back to the top for both participants.
    reply = client.post(
        f"/api/messages/threads/{older_thread}/reply", headers=host_headers, json={"body": "Yes, available"}
    )
    assert reply.status_code == 201
    assert reply.json()["to_id"] == renter["user"]["id"]

    renter_threads = client.get("/api/messages/threads", headers=renter_headers).json()
    assert renter_threads[0]["thread_id"] == older_thread
    assert renter_threads[0]["unread_count"] == 1


def test_reply_rejects_empty_and_caps_length(client, signup):
    host = signup("host-reply-validation@example.com", role="host")
    renter = signup("renter-reply-validation@example.com", role="renter")
    listing = _create_listing(client, host["access_token"])

    thread_id = client.post(
        "/api/messages",
        headers=_auth_header(renter["access_token"]),
        json={"listing_id": listing["id"], "body": "Hi"},
    ).json()["thread_id"]

    empty = client.post(
        f"/api/messages/threads/{thread_id}/reply",
        headers=_auth_header(host["access_token"]),
        json={"body": "  \n "},
    )
    assert empty.status_code == 422

    long = client.post(
        f"/api/messages/threads/{thread_id}/reply",
        headers=_auth_header(host["access_token"]),
        json={"body": "y" * 2500},
    )
    assert long.status_code == 201
    assert len(long.json()["body"]) == 2000


def test_messages_require_authentication(client):
    assert client.get("/api/messages/threads").status_code == 401
    assert client.get("/api/messages/threads/anything").status_code == 401
    assert client.post("/api/messages", json={"listing_id": "x", "body": "hi"}).status_code == 401
