from datetime import datetime, timezone


def test_register_new_user(unauthenticated_client):
    response = unauthenticated_client.post(
        "/auth/register", json={"email": "new@example.com", "password": "supersecure123"}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "new@example.com"
    assert "hashed_password" not in body
    assert "password" not in body


def test_register_duplicate_email_rejected(unauthenticated_client):
    unauthenticated_client.post(
        "/auth/register", json={"email": "dupe@example.com", "password": "supersecure123"}
    )
    response = unauthenticated_client.post(
        "/auth/register", json={"email": "dupe@example.com", "password": "anotherpassword"}
    )
    assert response.status_code == 400


def test_register_short_password_rejected(unauthenticated_client):
    response = unauthenticated_client.post(
        "/auth/register", json={"email": "shortpw@example.com", "password": "short"}
    )
    assert response.status_code == 422


def test_login_success(unauthenticated_client):
    unauthenticated_client.post(
        "/auth/register", json={"email": "login@example.com", "password": "supersecure123"}
    )
    response = unauthenticated_client.post(
        "/auth/login", data={"username": "login@example.com", "password": "supersecure123"}
    )
    assert response.status_code == 200
    assert "access_token" in response.json()
    assert response.json()["token_type"] == "bearer"


def test_login_wrong_password_rejected(unauthenticated_client):
    unauthenticated_client.post(
        "/auth/register", json={"email": "wrongpw@example.com", "password": "supersecure123"}
    )
    response = unauthenticated_client.post(
        "/auth/login", data={"username": "wrongpw@example.com", "password": "nope"}
    )
    assert response.status_code == 401


def test_login_unknown_user_rejected(unauthenticated_client):
    response = unauthenticated_client.post(
        "/auth/login", data={"username": "ghost@example.com", "password": "whatever123"}
    )
    assert response.status_code == 401


def test_protected_route_requires_token(unauthenticated_client):
    response = unauthenticated_client.get("/clients")
    assert response.status_code == 401


def test_protected_route_rejects_garbage_token(unauthenticated_client):
    unauthenticated_client.headers.update({"Authorization": "Bearer not-a-real-token"})
    response = unauthenticated_client.get("/clients")
    assert response.status_code == 401


# ---- cross-user data isolation ---------------------------------------------

def test_users_cannot_see_each_others_clients(client, second_user_client):
    client.post("/clients", json={"name": "My Client", "email": "myclient@example.com"})
    response = second_user_client.get("/clients")
    assert response.status_code == 200
    assert response.json() == []


def test_users_cannot_access_each_others_client_by_id(client, second_user_client):
    created = client.post("/clients", json={"name": "My Client", "email": "myclient2@example.com"}).json()
    response = second_user_client.get(f"/clients/{created['id']}")
    assert response.status_code == 404


def test_users_cannot_delete_each_others_clients(client, second_user_client):
    created = client.post("/clients", json={"name": "My Client", "email": "myclient3@example.com"}).json()
    response = second_user_client.delete(f"/clients/{created['id']}")
    assert response.status_code == 404
    # confirm it's still there for the actual owner
    assert client.get(f"/clients/{created['id']}").status_code == 200


def _invoice_payload(client_id):
    now = datetime.now(timezone.utc)
    return {
        "client_id": client_id,
        "issue_date": now.isoformat(),
        "due_date": now.isoformat(),
        "tax_rate": "0",
        "line_items": [],
    }


def test_users_cannot_see_each_others_invoices(client, second_user_client):
    c = client.post("/clients", json={"name": "Owned Client", "email": "ownedclient@example.com"}).json()
    client.post("/invoices", json=_invoice_payload(c["id"]))

    response = second_user_client.get("/invoices")
    assert response.status_code == 200
    assert response.json() == []


def test_users_cannot_access_each_others_invoice_by_id(client, second_user_client):
    c = client.post("/clients", json={"name": "Owned Client", "email": "ownedclient2@example.com"}).json()
    invoice = client.post("/invoices", json=_invoice_payload(c["id"])).json()

    response = second_user_client.get(f"/invoices/{invoice['id']}")
    assert response.status_code == 404


def test_cannot_create_invoice_for_another_users_client(client, second_user_client):
    c = client.post("/clients", json={"name": "Owned Client", "email": "ownedclient3@example.com"}).json()
    response = second_user_client.post("/invoices", json=_invoice_payload(c["id"]))
    assert response.status_code == 404


def test_users_cannot_download_each_others_invoice_pdf(client, second_user_client):
    c = client.post("/clients", json={"name": "Owned Client", "email": "ownedclient4@example.com"}).json()
    invoice = client.post("/invoices", json=_invoice_payload(c["id"])).json()

    response = second_user_client.get(f"/invoices/{invoice['id']}/pdf")
    assert response.status_code == 404
