"""Direct function-call debug script for Phase 3.

运行方式：
    docker compose exec api python scripts/debug_direct_phase3_flow.py

这个脚本不走 HTTP，不经过 router，也不校验 X-Internal-API-Key。
它直接调用 service，适合单步调试：
InternalTicketCreate -> TicketService -> repositories -> PostgreSQL。
"""

import uuid

from app.db.session import SessionLocal
from app.models.ticket import TicketPriority, TicketType
from app.repositories.agent_trace_repo import (
    AgentToolCallRepository,
    PendingActionExecutionRepository,
    TicketPolicyReferenceRepository,
)
from app.schemas.agent_trace import RagReferenceCreate
from app.schemas.ticket import InternalTicketCreate
from app.services.ticket_service import TicketService


def print_line(title: str) -> None:
    print("\n" + "=" * 100)
    print(title)
    print("=" * 100)


def build_payload(unique: str) -> InternalTicketCreate:
    """构造标准第三阶段 Internal API payload。"""
    return InternalTicketCreate(
        external_session_id=f"debug-session-{unique}",
        pending_action_id=f"pa-debug-{unique}",
        idempotency_key=f"agent:pa-debug-{unique}:create_ticket",
        trace_id=f"trace-debug-{unique}",
        tool_call_id=f"tool-call-debug-{unique}",
        tool_name="create_hr_ticket",
        ticket_type=TicketType.leave_request,
        title="Phase3 Direct Debug 年假申请",
        description="这是直接调用 service 创建的第三阶段调试工单。",
        priority=TicketPriority.normal,
        created_by_external=f"agent:debug-session-{unique}",
        confirmed_by_external="user:debug-user-001",
        confirmed_at="2026-05-13T10:30:00Z",
        rag_answer_snapshot="根据员工年假管理制度，员工申请年假应提前提交申请。",
        rag_references=[
            RagReferenceCreate(
                rag_query="年假申请规则",
                document_id="doc-annual-leave",
                document_name="员工年假管理制度.pdf",
                chunk_id="chunk-001",
                breadcrumb="第二章 > 第三条",
                page_number=4,
                retrieval_score=0.87,
                content_snapshot="员工申请年假应提前提交申请，并经 HR 审核。",
            )
        ],
        agent_trace={
            "agent_type": "function_calling",
            "llm": "qwen",
            "steps": [
                {"type": "tool_call", "tool_name": "rag_search", "output_summary": "命中年假制度"},
                {"type": "pending_action", "action_type": "create_hr_ticket", "requires_confirmation": True},
            ],
        },
    )


def main() -> None:
    db = SessionLocal()
    try:
        unique = uuid.uuid4().hex[:8]
        payload = build_payload(unique)

        print_line("1. 首次调用 TicketService.create_ticket_from_internal")
        ticket = TicketService.create_ticket_from_internal(db, payload=payload)
        print("ticket.id =", ticket.id)
        print("ticket.ticket_no =", ticket.ticket_no)
        print("ticket.pending_action_id =", ticket.pending_action_id)
        print("ticket.idempotency_key =", ticket.idempotency_key)

        print_line("2. 查询 pending_action_executions")
        execution = PendingActionExecutionRepository.get_by_pending_action_id(db, payload.pending_action_id)
        print("execution.status =", execution.status)
        print("execution.result_resource_type =", execution.result_resource_type)
        print("execution.result_resource_id =", execution.result_resource_id)

        print_line("3. 查询 agent_tool_calls")
        tool_calls, total = AgentToolCallRepository.list_all(db, offset=0, limit=10)
        print("tool_call_total =", total)
        latest = tool_calls[0]
        print("latest.tool_name =", latest.tool_name)
        print("latest.status =", latest.status)
        print("latest.trace_id =", latest.trace_id)
        print("latest.tool_call_id =", latest.tool_call_id)
        print("latest.latency_ms =", latest.latency_ms)

        print_line("4. 查询 ticket_policy_references")
        references = TicketPolicyReferenceRepository.list_by_ticket_id(db, ticket_id=ticket.id)
        for ref in references:
            print(
                {
                    "document_id": ref.document_id,
                    "document_name": ref.document_name,
                    "chunk_id": ref.chunk_id,
                    "breadcrumb": ref.breadcrumb,
                    "retrieval_score": ref.retrieval_score,
                }
            )

        print_line("5. 再次调用同一个 payload，验证 replayed")
        replayed_ticket = TicketService.create_ticket_from_internal(db, payload=payload)
        print("replayed_ticket.id =", replayed_ticket.id)
        print("same_ticket =", replayed_ticket.id == ticket.id)

        tool_calls, total = AgentToolCallRepository.list_all(db, offset=0, limit=10)
        print("tool_call_statuses =", [item.status.value for item in tool_calls])

    finally:
        db.close()


if __name__ == "__main__":
    main()
