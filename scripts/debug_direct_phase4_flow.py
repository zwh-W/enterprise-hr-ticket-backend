"""Direct function-call debug script for Phase 4.

这个脚本不走 HTTP，不走 Swagger，直接调用 service 层。
适合用 IDE 断点观察：状态机、transition record、audit log 如何在一个事务里写入。

运行方式：
    docker compose exec api python scripts/debug_direct_phase4_flow.py
"""

import uuid

from app.db.session import SessionLocal
from app.models.user import UserRole
from app.repositories.ticket_transition_repo import TicketStatusTransitionRepository
from app.schemas.auth import LoginRequest, RegisterRequest
from app.schemas.ticket import TicketCreate
from app.schemas.ticket_transition import TicketAssignRequest, TicketCancelRequest, TicketStatusUpdate
from app.models.ticket import TicketPriority, TicketStatus, TicketType
from app.services.auth_service import AuthService
from app.services.ticket_service import TicketService


def line(title: str) -> None:
    print("\n" + "=" * 90)
    print(title)
    print("=" * 90)


def register_and_login(db, *, email: str, username: str, role: UserRole):
    user = AuthService.register(
        db,
        RegisterRequest(email=email, username=username, password="Password123!", role=role),
    )
    token = AuthService.login(db, LoginRequest(email=email, password="Password123!"))
    print(f"created user: {email}, role={role.value}, token_prefix={token.access_token[:12]}")
    return user


def main() -> None:
    db = SessionLocal()
    try:
        suffix = uuid.uuid4().hex[:8]

        line("1. 创建 employee / hr 用户")
        employee = register_and_login(
            db,
            email=f"phase4_employee_{suffix}@example.com",
            username=f"phase4_employee_{suffix}",
            role=UserRole.employee,
        )
        hr = register_and_login(
            db,
            email=f"phase4_hr_{suffix}@example.com",
            username=f"phase4_hr_{suffix}",
            role=UserRole.hr,
        )

        line("2. employee 创建 open 工单")
        ticket = TicketService.create_ticket_for_user(
            db,
            payload=TicketCreate(
                ticket_type=TicketType.general_hr,
                title="Phase4 状态机 Debug 工单",
                description="用于直接调用 service 验证状态流转。",
                priority=TicketPriority.normal,
            ),
            creator=employee,
        )
        print("ticket:", ticket.ticket_no, ticket.status.value, ticket.creator_id)

        line("3. hr 分配工单给自己")
        ticket = TicketService.assign_ticket(
            db,
            ticket_id=ticket.id,
            payload=TicketAssignRequest(assignee_id=hr.id, reason="debug assign to HR"),
            current_user=hr,
        )
        print("assignee_id:", ticket.assignee_id)

        line("4. hr 执行 open -> processing")
        ticket = TicketService.update_status(
            db,
            ticket_id=ticket.id,
            payload=TicketStatusUpdate(status=TicketStatus.processing, reason="HR 接单处理"),
            current_user=hr,
        )
        print("status:", ticket.status.value)

        line("5. hr 执行 processing -> resolved")
        ticket = TicketService.update_status(
            db,
            ticket_id=ticket.id,
            payload=TicketStatusUpdate(status=TicketStatus.resolved, reason="HR 已处理完成"),
            current_user=hr,
        )
        print("status:", ticket.status.value)

        line("6. employee 执行 resolved -> closed")
        ticket = TicketService.update_status(
            db,
            ticket_id=ticket.id,
            payload=TicketStatusUpdate(status=TicketStatus.closed, reason="员工确认关闭"),
            current_user=employee,
        )
        print("status:", ticket.status.value)

        line("7. 查询 transition history")
        transitions = TicketStatusTransitionRepository.list_by_ticket_id(db, ticket_id=ticket.id)
        for item in transitions:
            print(
                {
                    "from": item.from_status.value,
                    "to": item.to_status.value,
                    "operator_role": item.operator_role.value,
                    "reason": item.reason,
                    "created_at": item.created_at.isoformat(),
                }
            )

        line("8. 再创建一张工单并取消")
        ticket2 = TicketService.create_ticket_for_user(
            db,
            payload=TicketCreate(
                ticket_type=TicketType.general_hr,
                title="Phase4 取消 Debug 工单",
                description="用于验证 open -> cancelled。",
                priority=TicketPriority.normal,
            ),
            creator=employee,
        )
        ticket2 = TicketService.cancel_ticket(
            db,
            ticket_id=ticket2.id,
            payload=TicketCancelRequest(reason="员工取消申请"),
            current_user=employee,
        )
        print("ticket2:", ticket2.ticket_no, ticket2.status.value)

    finally:
        db.close()


if __name__ == "__main__":
    main()
