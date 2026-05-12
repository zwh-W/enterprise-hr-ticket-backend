from tests.conftest import auth_headers, login_user, register_user


def test_employee_can_create_and_read_own_ticket(client):
    register_user(client, email="employee@example.com", username="employee01")
    token = login_user(client, email="employee@example.com")

    create_response = client.post(
        "/tickets",
        headers=auth_headers(token),
        json={
            "ticket_type": "leave_request",
            "title": "年假申请",
            "description": "申请年假 3 天",
            "priority": "normal",
        },
    )
    assert create_response.status_code == 201
    ticket = create_response.json()
    assert ticket["ticket_no"].startswith("HR-")
    assert ticket["status"] == "open"

    list_response = client.get("/tickets", headers=auth_headers(token))
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1

    detail_response = client.get(f"/tickets/{ticket['id']}", headers=auth_headers(token))
    assert detail_response.status_code == 200
    assert detail_response.json()["id"] == ticket["id"]


def test_anonymous_user_cannot_create_ticket(client):
    response = client.post(
        "/tickets",
        json={
            "ticket_type": "leave_request",
            "title": "年假申请",
            "description": "申请年假 3 天",
            "priority": "normal",
        },
    )
    assert response.status_code == 401
