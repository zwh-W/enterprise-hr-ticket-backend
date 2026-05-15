"""Phase 4 tests: ticket state machine and transition history."""

from tests.conftest import auth_headers, login_user, register_user


def create_ticket(client, token, title="状态机测试工单"):
    response = client.post(
        "/tickets",
        headers=auth_headers(token),
        json={
            "ticket_type": "general_hr",
            "title": title,
            "description": "用于第四阶段状态机测试。",
            "priority": "normal",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_hr_can_move_open_to_processing_and_processing_to_resolved(client):
    register_user(client, email="employee@example.com", username="employee01")
    register_user(client, email="hr@example.com", username="hr01", role="hr")
    employee_token = login_user(client, email="employee@example.com")
    hr_token = login_user(client, email="hr@example.com")

    ticket = create_ticket(client, employee_token)

    response = client.patch(
        f"/tickets/{ticket['id']}/status",
        headers=auth_headers(hr_token),
        json={"status": "processing", "reason": "HR 接单处理"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "processing"

    response = client.patch(
        f"/tickets/{ticket['id']}/status",
        headers=auth_headers(hr_token),
        json={"status": "resolved", "reason": "问题已处理"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "resolved"

    transitions = client.get(f"/tickets/{ticket['id']}/transitions", headers=auth_headers(hr_token))
    assert transitions.status_code == 200, transitions.text
    items = transitions.json()["items"]
    assert len(items) == 2
    assert items[0]["from_status"] == "open"
    assert items[0]["to_status"] == "processing"
    assert items[1]["from_status"] == "processing"
    assert items[1]["to_status"] == "resolved"


def test_employee_cannot_resolve_own_ticket_directly(client):
    register_user(client, email="employee@example.com", username="employee01")
    employee_token = login_user(client, email="employee@example.com")
    ticket = create_ticket(client, employee_token)

    response = client.patch(
        f"/tickets/{ticket['id']}/status",
        headers=auth_headers(employee_token),
        json={"status": "resolved", "reason": "员工不能直接解决"},
    )

    # open -> resolved 本身不是合法状态边，返回 409。
    assert response.status_code == 409
    assert response.json()["code"] == "CONFLICT"


def test_employee_can_cancel_own_open_ticket(client):
    register_user(client, email="employee@example.com", username="employee01")
    employee_token = login_user(client, email="employee@example.com")
    ticket = create_ticket(client, employee_token)

    response = client.post(
        f"/tickets/{ticket['id']}/cancel",
        headers=auth_headers(employee_token),
        json={"reason": "不需要处理了"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "cancelled"

    transitions = client.get(f"/tickets/{ticket['id']}/transitions", headers=auth_headers(employee_token))
    assert transitions.status_code == 200, transitions.text
    assert transitions.json()["items"][0]["to_status"] == "cancelled"


def test_cancelled_ticket_cannot_be_processed(client):
    register_user(client, email="employee@example.com", username="employee01")
    register_user(client, email="hr@example.com", username="hr01", role="hr")
    employee_token = login_user(client, email="employee@example.com")
    hr_token = login_user(client, email="hr@example.com")
    ticket = create_ticket(client, employee_token)

    cancel_response = client.post(
        f"/tickets/{ticket['id']}/cancel",
        headers=auth_headers(employee_token),
        json={"reason": "取消申请"},
    )
    assert cancel_response.status_code == 200

    response = client.patch(
        f"/tickets/{ticket['id']}/status",
        headers=auth_headers(hr_token),
        json={"status": "processing", "reason": "尝试处理已取消工单"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "CONFLICT"


def test_hr_can_assign_ticket_to_hr_user(client):
    register_user(client, email="employee@example.com", username="employee01")
    register_user(client, email="hr1@example.com", username="hr01", role="hr")
    register_user(client, email="hr2@example.com", username="hr02", role="hr")

    employee_token = login_user(client, email="employee@example.com")
    hr1_token = login_user(client, email="hr1@example.com")
    hr2_token = login_user(client, email="hr2@example.com")

    ticket = create_ticket(client, employee_token)
    me_response = client.get("/users/me", headers=auth_headers(hr2_token))
    assignee_id = me_response.json()["id"]

    response = client.patch(
        f"/tickets/{ticket['id']}/assign",
        headers=auth_headers(hr1_token),
        json={"assignee_id": assignee_id, "reason": "分配给 HR2"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["assignee_id"] == assignee_id
