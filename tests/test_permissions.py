from tests.conftest import auth_headers, login_user, register_user


def create_ticket(client, token, title):
    response = client.post(
        "/tickets",
        headers=auth_headers(token),
        json={
            "ticket_type": "general_hr",
            "title": title,
            "description": "测试工单",
            "priority": "normal",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_employee_cannot_view_other_employee_ticket(client):
    register_user(client, email="a@example.com", username="employee_a")
    register_user(client, email="b@example.com", username="employee_b")
    token_a = login_user(client, email="a@example.com")
    token_b = login_user(client, email="b@example.com")

    ticket = create_ticket(client, token_a, "A 的工单")

    response = client.get(f"/tickets/{ticket['id']}", headers=auth_headers(token_b))
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


def test_hr_can_view_all_tickets(client):
    register_user(client, email="employee@example.com", username="employee01", role="employee")
    register_user(client, email="hr@example.com", username="hr01", role="hr")
    employee_token = login_user(client, email="employee@example.com")
    hr_token = login_user(client, email="hr@example.com")

    ticket = create_ticket(client, employee_token, "员工工单")

    detail_response = client.get(f"/tickets/{ticket['id']}", headers=auth_headers(hr_token))
    assert detail_response.status_code == 200

    list_response = client.get("/tickets", headers=auth_headers(hr_token))
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1
