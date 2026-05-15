"""Phase 3 tests: Agent trace, pending_action execution and RAG evidence.

这些测试不追求覆盖所有 CRUD，而是覆盖 AI Workflow Backend 最关键的风险点：
- 创建真实 ticket 时是否保存 Agent 执行链路。
- 重复请求是否记录 replayed。
- 冲突请求是否记录 conflict。
- employee 是否不能查看 Agent trace。
"""

from tests.conftest import auth_headers, login_user, register_user


def phase3_internal_payload(idempotency_key: str = "agent:pa-phase3-001:create_ticket"):
    """构造第三阶段标准 Internal API 请求体。"""
    return {
        "external_session_id": "session-phase3-001",
        "pending_action_id": "pa-phase3-001",
        "idempotency_key": idempotency_key,
        "trace_id": "trace-phase3-001",
        "tool_call_id": "tool-call-phase3-001",
        "tool_name": "create_hr_ticket",
        "ticket_type": "leave_request",
        "title": "年假申请：5月11日-13日",
        "description": "申请年假 3 天，时间为 2026 年 5 月 11 日至 5 月 13 日。",
        "priority": "normal",
        "created_by_external": "agent:session-phase3-001",
        "confirmed_by_external": "user:employee-001",
        "confirmed_at": "2026-05-13T10:30:00Z",
        "rag_answer_snapshot": "根据员工年假管理制度，员工申请年假应提前提交申请。",
        "rag_references": [
            {
                "rag_query": "年假申请规则",
                "document_id": "doc-annual-leave",
                "document_name": "员工年假管理制度.pdf",
                "chunk_id": "chunk-001",
                "breadcrumb": "第二章 > 第三条",
                "page_number": 4,
                "retrieval_score": 0.87,
                "content_snapshot": "员工申请年假应提前提交申请，并经 HR 审核。",
            }
        ],
        "agent_trace": {
            "agent_type": "function_calling",
            "llm": "qwen",
            "steps": [
                {"type": "tool_call", "tool_name": "rag_search", "output_summary": "命中年假制度"},
                {"type": "pending_action", "action_type": "create_hr_ticket", "requires_confirmation": True},
            ],
        },
    }


def create_hr_user_and_headers(client):
    """创建 HR 用户并返回 JWT headers。"""
    register_user(client, email="hr@example.com", username="hr01", role="hr")
    token = login_user(client, email="hr@example.com")
    return auth_headers(token)


def test_internal_create_writes_agent_trace_execution_and_policy_references(client):
    """首次创建工单时，应同时写入 ticket、tool_call、pending_action_execution、RAG evidence。"""
    response = client.post(
        "/internal/tickets",
        headers={"X-Internal-API-Key": "test-internal-key"},
        json=phase3_internal_payload(),
    )
    assert response.status_code == 201, response.text
    ticket_id = response.json()["id"]

    hr_headers = create_hr_user_and_headers(client)

    tool_calls = client.get("/agent-tool-calls", headers=hr_headers)
    assert tool_calls.status_code == 200
    assert tool_calls.json()["total"] == 1
    assert tool_calls.json()["items"][0]["status"] == "succeeded"
    assert tool_calls.json()["items"][0]["tool_name"] == "create_hr_ticket"

    executions = client.get("/pending-action-executions", headers=hr_headers)
    assert executions.status_code == 200
    assert executions.json()["total"] == 1
    assert executions.json()["items"][0]["status"] == "succeeded"
    assert executions.json()["items"][0]["result_resource_type"] == "ticket"

    references = client.get(f"/tickets/{ticket_id}/policy-references", headers=hr_headers)
    assert references.status_code == 200
    assert len(references.json()["items"]) == 1
    assert references.json()["items"][0]["document_id"] == "doc-annual-leave"
    assert references.json()["items"][0]["chunk_id"] == "chunk-001"


def test_repeated_internal_request_records_replayed_tool_call_and_execution(client):
    """相同 key + 相同 payload 不重复建单，但要记录 replayed 调用。"""
    payload = phase3_internal_payload("agent:pa-phase3-replay:create_ticket")

    first = client.post("/internal/tickets", headers={"X-Internal-API-Key": "test-internal-key"}, json=payload)
    second = client.post("/internal/tickets", headers={"X-Internal-API-Key": "test-internal-key"}, json=payload)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]

    hr_headers = create_hr_user_and_headers(client)
    tool_calls = client.get("/agent-tool-calls", headers=hr_headers)
    executions = client.get("/pending-action-executions", headers=hr_headers)

    assert tool_calls.status_code == 200
    assert executions.status_code == 200
    statuses = [item["status"] for item in tool_calls.json()["items"]]
    execution_statuses = [item["status"] for item in executions.json()["items"]]

    assert "succeeded" in statuses
    assert "replayed" in statuses
    assert "succeeded" in execution_statuses
    assert "idempotent_replayed" in execution_statuses


def test_conflict_internal_request_records_conflict_trace(client):
    """相同 key + 不同 payload 返回 409，并记录 conflict 调用。"""
    payload = phase3_internal_payload("agent:pa-phase3-conflict:create_ticket")
    first = client.post("/internal/tickets", headers={"X-Internal-API-Key": "test-internal-key"}, json=payload)
    assert first.status_code == 201

    changed_payload = {**payload, "title": "被篡改的年假申请标题"}
    conflict = client.post(
        "/internal/tickets",
        headers={"X-Internal-API-Key": "test-internal-key"},
        json=changed_payload,
    )
    assert conflict.status_code == 409

    hr_headers = create_hr_user_and_headers(client)
    tool_calls = client.get("/agent-tool-calls", headers=hr_headers)
    executions = client.get("/pending-action-executions", headers=hr_headers)

    assert "conflict" in [item["status"] for item in tool_calls.json()["items"]]
    assert "conflict" in [item["status"] for item in executions.json()["items"]]


def test_employee_cannot_view_agent_trace_records(client):
    """employee 不能查看 Agent trace 和 pending_action 执行记录。"""
    register_user(client, email="employee@example.com", username="employee01", role="employee")
    token = login_user(client, email="employee@example.com")
    headers = auth_headers(token)

    tool_calls = client.get("/agent-tool-calls", headers=headers)
    executions = client.get("/pending-action-executions", headers=headers)

    assert tool_calls.status_code == 403
    assert executions.status_code == 403
