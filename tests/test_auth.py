"""Authentication tests."""

from tests.conftest import auth_headers, login_user, register_user


def test_register_login_and_me(client):
    response = register_user(client, email="employee@example.com", username="employee01")
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "employee@example.com"
    assert body["role"] == "employee"
    assert "hashed_password" not in body

    token = login_user(client, email="employee@example.com")
    me_response = client.get("/users/me", headers=auth_headers(token))
    assert me_response.status_code == 200
    assert me_response.json()["email"] == "employee@example.com"


def test_swagger_token_login_uses_form_data(client):
    """Swagger Authorize 调用的是 /auth/token，而不是 JSON /auth/login。"""
    register_user(client, email="employee@example.com", username="employee01")

    response = client.post(
        "/auth/token",
        data={"username": "employee@example.com", "password": "Password123!"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"
    assert response.json()["access_token"]


def test_register_duplicate_email_returns_conflict(client):
    register_user(client, email="employee@example.com", username="employee01")
    response = register_user(client, email="employee@example.com", username="employee02")
    assert response.status_code == 409
    assert response.json()["code"] == "CONFLICT"


def test_login_with_wrong_password_returns_unauthorized(client):
    register_user(client, email="employee@example.com", username="employee01")
    response = client.post("/auth/login", json={"email": "employee@example.com", "password": "WrongPass123!"})
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"
