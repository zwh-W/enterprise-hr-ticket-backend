"""Direct function-call debug script for phase 2.

运行方式：
    docker compose exec api python scripts/debug_direct_phase2_flow.py

这个脚本不走 HTTP，不走 FastAPI router，直接调用 Service / Repository。
它用于观察第二阶段幂等数据流：
InternalTicketCreate -> TicketService -> IdempotencyRepository -> TicketRepository -> AuditRepository -> DB
"""

import uuid

from app.db.session import SessionLocal
from app.repositories.idempotency_repo import IdempotencyRepository
from app.repositories.ticket_repo import TicketRepository
from app.schemas.ticket import InternalTicketCreate
from app.services.ticket_service import TicketService


def line(title: str) -> None:
    """打印分隔标题。"""
    print("\n" + "=" * 100)
    print(title)
    print("=" * 100)


def main() -> None:
    """直接调用第二阶段核心函数。"""
    db = SessionLocal()
    try:
        unique = uuid.uuid4().hex[:8]
        idem_key = f"agent:debug-pa-{unique}:create_ticket"

        line("1. 构造 InternalTicketCreate")
        payload = InternalTicketCreate(
            external_session_id=f"debug-session-{unique}",
            pending_action_id=f"debug-pa-{unique}",
            idempotency_key=idem_key,
            ticket_type="leave_request",
            title="Direct Phase2 Debug 年假申请",
            description="直接调用 service 创建的 Internal API 工单，用于观察幂等数据流。",
            created_by_external=f"agent:debug-session-{unique}",
        )
        print(payload)

        line("2. 第一次调用 TicketService.create_ticket_from_internal")
        first_ticket = TicketService.create_ticket_from_internal(db, payload=payload)
        print("first_ticket.id =", first_ticket.id)
        print("first_ticket.ticket_no =", first_ticket.ticket_no)
        print("first_ticket.idempotency_key =", first_ticket.idempotency_key)

        line("3. 查询 idempotency_keys 表")
        idem = IdempotencyRepository.get_by_key(db, idem_key)
        print("idem.id =", idem.id)
        print("idem.key =", idem.key)
        print("idem.request_hash =", idem.request_hash)
        print("idem.status =", idem.status)
        print("idem.resource_type =", idem.resource_type)
        print("idem.resource_id =", idem.resource_id)
        print("idem.response_body =", idem.response_body)

        line("4. 使用相同 payload 第二次调用，应返回同一个 ticket")
        second_ticket = TicketService.create_ticket_from_internal(db, payload=payload)
        print("second_ticket.id =", second_ticket.id)
        print("second_ticket.ticket_no =", second_ticket.ticket_no)
        print("same ticket? =", second_ticket.id == first_ticket.id)

        line("5. 直接通过 TicketRepository 查询")
        ticket_from_repo = TicketRepository.get_by_idempotency_key(db, idem_key)
        print("ticket_from_repo.id =", ticket_from_repo.id)
        print("ticket_from_repo.ticket_no =", ticket_from_repo.ticket_no)

        line("6. 使用相同 idempotency_key 但修改 title，应触发 ConflictException")
        conflict_payload = payload.model_copy(update={"title": "被修改的标题"})
        try:
            TicketService.create_ticket_from_internal(db, payload=conflict_payload)
        except Exception as exc:
            print("conflict exception type =", type(exc).__name__)
            print("conflict exception =", exc)

    finally:
        db.close()


if __name__ == "__main__":
    main()
