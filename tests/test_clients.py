def test_create_client(client):
    response = client.post("/clients", json={
        "name": "Ada Lovelace",
        "email": "ada@example.com",
        "phone": "555-0100",
        "address": "12 Analytical Engine Way",
    })
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Ada Lovelace"
    assert "id" in body
    assert "created_at" in body


def test_create_client_invalid_email(client):
    response = client.post("/clients", json={"name": "Bad Email", "email": "not-an-email"})
    assert response.status_code == 422


def test_list_clients(client):
    client.post("/clients", json={"name": "Client A", "email": "a@example.com"})
    client.post("/clients", json={"name": "Client B", "email": "b@example.com"})
    response = client.get("/clients")
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_get_client(client):
    created = client.post("/clients", json={"name": "Grace Hopper", "email": "grace@example.com"}).json()
    response = client.get(f"/clients/{created['id']}")
    assert response.status_code == 200
    assert response.json()["name"] == "Grace Hopper"


def test_get_client_404(client):
    response = client.get("/clients/does-not-exist")
    assert response.status_code == 404


def test_update_client(client):
    created = client.post("/clients", json={"name": "Old Name", "email": "old@example.com"}).json()
    response = client.patch(f"/clients/{created['id']}", json={"name": "New Name"})
    assert response.status_code == 200
    assert response.json()["name"] == "New Name"
    assert response.json()["email"] == "old@example.com"  # unset fields untouched


def test_delete_client(client):
    created = client.post("/clients", json={"name": "Temp", "email": "temp@example.com"}).json()
    response = client.delete(f"/clients/{created['id']}")
    assert response.status_code == 204
    assert client.get(f"/clients/{created['id']}").status_code == 404
