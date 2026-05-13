"""Internal API tests.

第二阶段重点测试幂等语义：
- key 正确时能创建工单。
- 相同 key + 相同 payload 不重复创建。
- 相同 key + 不同 payload 返回 409。
"""

from tests.conftest import auth_headers, login_user, register_user


def internal_payload(idempotency_key: str = "agent:pa-test-001:create_ticket"):
    """构造 Internal API 测试请求体。"""
    return {
        "external_session_id": "test-session-ticket-001",
        "pending_action_id": "pa-test-001",
        "idempotency_key": idempotency_key,
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
    assert body["pending_action_id"] == "pa-test-001"
    assert body["idempotency_key"] == "agent:pa-test-001:create_ticket"


def test_internal_api_is_idempotent_for_same_payload(client):
    payload = internal_payload("agent:pa-test-duplicate:create_ticket")

    first_response = client.post(
        "/internal/tickets",
        headers={"X-Internal-API-Key": "test-internal-key"},
        json=payload,
    )
    second_response = client.post(
        "/internal/tickets",
        headers={"X-Internal-API-Key": "test-internal-key"},
        json=payload,
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 201
    assert second_response.json()["id"] == first_response.json()["id"]
    assert second_response.json()["ticket_no"] == first_response.json()["ticket_no"]

    register_user(client, email="hr@example.com", username="hr01", role="hr")
    token = login_user(client, email="hr@example.com")
    list_response = client.get("/tickets", headers=auth_headers(token))

    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1


def test_internal_api_rejects_same_key_with_different_payload(client):
    payload = internal_payload("agent:pa-test-conflict:create_ticket")

    first_response = client.post(
        "/internal/tickets",
        headers={"X-Internal-API-Key": "test-internal-key"},
        json=payload,
    )
    assert first_response.status_code == 201

    changed_payload = {**payload, "title": "被篡改的标题"}
    conflict_response = client.post(
        "/internal/tickets",
        headers={"X-Internal-API-Key": "test-internal-key"},
        json=changed_payload,
    )

    assert conflict_response.status_code == 409
    assert conflict_response.json()["code"] == "CONFLICT"


def test_hr_can_see_internal_ticket(client):
    client.post(
        "/internal/tickets",
        headers={"X-Internal-API-Key": "test-internal-key"},
        json=internal_payload("agent:pa-test-hr-visible:create_ticket"),
    )
    register_user(client, email="hr@example.com", username="hr01", role="hr")
    token = login_user(client, email="hr@example.com")

    response = client.get("/tickets", headers=auth_headers(token))
    assert response.status_code == 200
    assert response.json()["total"] == 1
