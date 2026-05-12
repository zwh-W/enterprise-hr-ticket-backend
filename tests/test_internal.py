from tests.conftest import auth_headers, login_user, register_user


def internal_payload():
    return {
        "external_session_id": "test-session-ticket-001",
        "ticket_type": "leave_request",
        "title": "年假申请：5月11日-13日",
        "description": "申请年假 3 天，时间为 2026 年 5 月 11 日至 5 月 13 日。",
        "created_by_external": "agent:test-session-ticket-001",
    }


def test_internal_api_rejects_invalid_key(client):
    response = client.post(
        "/internal/tickets",
        headers={"X-Internal-API-Key": "wrong-key"},
        json=internal_payload(),
    )
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


def test_internal_api_can_create_ticket(client):
    response = client.post(
        "/internal/tickets",
        headers={"X-Internal-API-Key": "test-internal-key"},
        json=internal_payload(),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["ticket_no"].startswith("HR-")
    assert body["status"] == "open"


def test_hr_can_see_internal_ticket(client):
    client.post(
        "/internal/tickets",
        headers={"X-Internal-API-Key": "test-internal-key"},
        json=internal_payload(),
    )
    register_user(client, email="hr@example.com", username="hr01", role="hr")
    token = login_user(client, email="hr@example.com")

    response = client.get("/tickets", headers=auth_headers(token))
    assert response.status_code == 200
    assert response.json()["total"] == 1
