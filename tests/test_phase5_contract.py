"""Phase 5 contract tests.

第五阶段重点不是新增业务功能，而是验证：
Agent/RAG 项目产生的数据可以通过 adapter 映射到 Backend Internal API 契约，
并完成真实 ticket 创建、trace/evidence 落库和状态流转。
"""

from app.integrations.agent_contract import (
    AgentConfirmResult,
    AgentPendingAction,
    AgentRagResult,
    AgentRagSource,
    AgentTraceContext,
    BackendTicketPayloadBuilder,
)
from tests.conftest import auth_headers, login_user, register_user


def build_demo_backend_payload():
    """用标准 Agent/RAG 抽象生成 Backend Internal API payload。"""
    pending_action = AgentPendingAction(
        pending_action_id="pa-phase5-001",
        session_id="session-phase5-001",
        action_type="create_hr_ticket",
        tool_name="create_hr_ticket",
        arguments={
            "ticket_type": "leave_request",
            "title": "年假申请：5月11日-13日",
            "description": "申请年假 3 天，时间为 2026 年 5 月 11 日至 5 月 13 日。",
            "priority": "normal",
        },
    )
    confirm_result = AgentConfirmResult(
        confirmed=True,
        confirmed_by="user:employee-001",
        confirmed_at="2026-05-13T10:30:00Z",
    )
    rag_result = AgentRagResult(
        query="员工年假申请规则",
        answer="根据员工年假管理制度，员工申请年假应提前提交申请。",
        sources=[
            AgentRagSource(
                document_id="doc-annual-leave",
                document_name="员工年假管理制度.pdf",
                chunk_id="chunk-001",
                breadcrumb="第二章 > 第三条",
                page_number=4,
                score=0.87,
                content="员工申请年假应提前提交申请，并经 HR 审核。",
            )
        ],
    )
    trace_context = AgentTraceContext(
        trace_id="trace-phase5-001",
        tool_call_id="tool-call-phase5-001",
        agent_trace={
            "agent_type": "function_calling",
            "steps": [
                {"type": "tool_call", "tool_name": "rag_search", "output_summary": "命中年假制度"},
                {"type": "pending_action", "requires_confirmation": True},
            ],
        },
    )
    return BackendTicketPayloadBuilder.build_internal_ticket_payload(
        pending_action=pending_action,
        confirm_result=confirm_result,
        rag_result=rag_result,
        trace_context=trace_context,
    )


def create_hr_headers(client):
    register_user(client, email="phase5-hr@example.com", username="phase5hr", role="hr")
    token = login_user(client, email="phase5-hr@example.com")
    return auth_headers(token)


def test_agent_contract_builder_generates_backend_payload():
    """Agent/RAG 数据应能稳定映射成 /internal/tickets 请求体。"""
    payload = build_demo_backend_payload()

    assert payload.external_session_id == "session-phase5-001"
    assert payload.pending_action_id == "pa-phase5-001"
    assert payload.idempotency_key == "agent:pa-phase5-001:create_ticket"
    assert payload.trace_id == "trace-phase5-001"
    assert payload.tool_call_id == "tool-call-phase5-001"
    assert payload.ticket_type.value == "leave_request"
    assert payload.rag_answer_snapshot is not None
    assert len(payload.rag_references) == 1
    assert payload.rag_references[0].document_id == "doc-annual-leave"


def test_phase5_contract_payload_can_create_ticket_and_status_flow(client):
    """标准契约 payload 应能完成三项目闭环的核心后端流程。"""
    payload = build_demo_backend_payload()
    hr_headers = create_hr_headers(client)

    created = client.post(
        "/internal/tickets",
        headers={"X-Internal-API-Key": "test-internal-key"},
        json=payload.model_dump(mode="json"),
    )
    assert created.status_code == 201, created.text
    ticket_id = created.json()["id"]

    tool_calls = client.get("/agent-tool-calls", headers=hr_headers)
    assert tool_calls.status_code == 200
    assert tool_calls.json()["items"][0]["trace_id"] == "trace-phase5-001"

    references = client.get(f"/tickets/{ticket_id}/policy-references", headers=hr_headers)
    assert references.status_code == 200
    assert references.json()["items"][0]["document_id"] == "doc-annual-leave"

    processing = client.patch(
        f"/tickets/{ticket_id}/status",
        headers=hr_headers,
        json={"status": "processing", "reason": "HR 开始处理"},
    )
    assert processing.status_code == 200

    transitions = client.get(f"/tickets/{ticket_id}/transitions", headers=hr_headers)
    assert transitions.status_code == 200
    assert transitions.json()["items"][0]["from_status"] == "open"
    assert transitions.json()["items"][0]["to_status"] == "processing"
