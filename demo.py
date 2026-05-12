import uuid

from app.core.security import decode_access_token
from app.db.session import SessionLocal
from app.repositories.user_repo import UserRepository
from app.repositories.ticket_repo import TicketRepository
from app.services.auth_service import AuthService
from app.services.ticket_service import TicketService
from app.services.audit_service import AuditService
from app.schemas.auth import RegisterRequest, LoginRequest
from app.schemas.ticket import TicketCreate, InternalTicketCreate
from app.models.user import UserRole
from app.models.ticket import TicketType, TicketPriority

def print_line(title: str) -> None:
    print("\n" + "=" * 100)
    print(title)
    print("=" * 100)


def main() -> None:
    db = SessionLocal()

    try:
        unique = uuid.uuid4().hex[:8]

        # ======================================================================
        # 1. 构造注册请求 schema
        # ======================================================================
        print_line("1. 构造 RegisterRequest")

        register_payload = RegisterRequest(
            email=f"debug_employee_{unique}@example.com",
            username=f"debug_employee_{unique}",
            password="Password123!",
            role=UserRole.employee,
        )

        print("register_payload =", register_payload)

        # 你可以在这里打断点
        # breakpoint()

        # ======================================================================
        # 2. 直接调用 AuthService.register()
        #    数据流：schema -> service -> repository -> model -> db
        # ======================================================================
        print_line("2. 调用 AuthService.register(db, register_payload)")

        user = AuthService.register(db, register_payload)

        print("user.id =", user.id)
        print("user.email =", user.email)
        print("user.username =", user.username)
        print("user.role =", user.role)
        print("user.hashed_password =", user.hashed_password)
        print("is password stored as plaintext? =", user.hashed_password == register_payload.password)

        # ======================================================================
        # 3. 直接调用 UserRepository 查询刚才创建的用户
        # ======================================================================
        print_line("3. 调用 UserRepository.get_by_email(db, email)")

        user_from_db = UserRepository.get_by_email(db, register_payload.email)

        print("user_from_db.id =", user_from_db.id)
        print("user_from_db.email =", user_from_db.email)

        # ======================================================================
        # 4. 构造登录请求 schema
        # ======================================================================
        print_line("4. 构造 LoginRequest")

        login_payload = LoginRequest(
            email=register_payload.email,
            password="Password123!",
        )

        print("login_payload =", login_payload)

        # ======================================================================
        # 5. 直接调用 AuthService.login()
        #    数据流：login schema -> service -> repo 查用户 -> 校验密码 -> 生成 JWT
        # ======================================================================
        print_line("5. 调用 AuthService.login(db, login_payload)")

        token = AuthService.login(db, login_payload)

        print("token.access_token =", token.access_token)
        print("token.token_type =", token.token_type)

        # ======================================================================
        # 6. 直接 decode JWT
        #    模拟 get_current_user 里的核心逻辑
        # ======================================================================
        print_line("6. decode_access_token(token.access_token)")

        payload = decode_access_token(token.access_token)

        print("jwt payload =", payload)

        user_id_from_token = payload.get("sub")
        current_user = UserRepository.get_by_id(db, uuid.UUID(user_id_from_token))

        print("current_user.id =", current_user.id)
        print("current_user.email =", current_user.email)
        print("current_user.role =", current_user.role)

        # ======================================================================
        # 7. 构造普通用户创建工单请求 schema
        # ======================================================================
        print_line("7. 构造 TicketCreate")

        ticket_payload = TicketCreate(
            ticket_type=TicketType.leave_request,
            title="Direct Debug 年假申请",
            description="这是直接调用 TicketService 创建的工单，不经过 HTTP 接口。",
            priority=TicketPriority.normal,
        )

        print("ticket_payload =", ticket_payload)

        # ======================================================================
        # 8. 直接调用 TicketService.create_ticket_for_user()
        #    数据流：schema + current_user -> service -> repo 创建 ticket -> repo 创建 audit_log -> commit
        # ======================================================================
        print_line("8. 调用 TicketService.create_ticket_for_user(db, payload, creator)")

        ticket = TicketService.create_ticket_for_user(
            db,
            payload=ticket_payload,
            creator=current_user,
        )

        print("ticket.id =", ticket.id)
        print("ticket.ticket_no =", ticket.ticket_no)
        print("ticket.ticket_type =", ticket.ticket_type)
        print("ticket.title =", ticket.title)
        print("ticket.status =", ticket.status)
        print("ticket.priority =", ticket.priority)
        print("ticket.creator_id =", ticket.creator_id)
        print("ticket.assignee_id =", ticket.assignee_id)
        print("ticket.external_session_id =", ticket.external_session_id)
        print("ticket.created_by_external =", ticket.created_by_external)

        # ======================================================================
        # 9. 直接调用 TicketRepository 查询工单
        # ======================================================================
        print_line("9. 调用 TicketRepository.get_by_id(db, ticket.id)")

        ticket_from_db = TicketRepository.get_by_id(db, ticket.id)

        print("ticket_from_db.id =", ticket_from_db.id)
        print("ticket_from_db.ticket_no =", ticket_from_db.ticket_no)
        print("ticket_from_db.status =", ticket_from_db.status)

        # ======================================================================
        # 10. 直接调用 TicketService.list_tickets()
        #     employee 只能看到自己创建的工单
        # ======================================================================
        print_line("10. 调用 TicketService.list_tickets(db, current_user, page, page_size)")

        tickets, total = TicketService.list_tickets(
            db,
            current_user=current_user,
            page=1,
            page_size=20,
        )

        print("total =", total)
        print("visible ticket_nos =", [item.ticket_no for item in tickets])

        # ======================================================================
        # 11. 直接调用 TicketService.get_ticket()
        #     内部会做权限判断
        # ======================================================================
        print_line("11. 调用 TicketService.get_ticket(db, ticket_id, current_user)")

        ticket_detail = TicketService.get_ticket(
            db,
            ticket_id=ticket.id,
            current_user=current_user,
        )

        print("ticket_detail.id =", ticket_detail.id)
        print("ticket_detail.title =", ticket_detail.title)

        # ======================================================================
        # 12. 构造 Internal API 创建工单 schema
        #     注意：这里不走 JWT，也不走 X-Internal-API-Key。
        #     因为我们是直接调用 service，不经过 router/deps。
        # ======================================================================
        print_line("12. 构造 InternalTicketCreate")

        internal_payload = InternalTicketCreate(
            external_session_id=f"debug-session-{unique}",
            ticket_type=TicketType.leave_request,
            title="Direct Debug Agent 年假申请",
            description="这是模拟 Agent pending_action 确认后直接调用 service 创建的工单。",
            created_by_external=f"agent:debug-session-{unique}",
            priority=TicketPriority.normal,
        )

        print("internal_payload =", internal_payload)

        # ======================================================================
        # 13. 直接调用 TicketService.create_ticket_from_internal()
        #     数据流：internal schema -> service -> repo 创建 ticket -> repo 创建 audit_log -> commit
        # ======================================================================
        print_line("13. 调用 TicketService.create_ticket_from_internal(db, payload)")

        internal_ticket = TicketService.create_ticket_from_internal(
            db,
            payload=internal_payload,
        )

        print("internal_ticket.id =", internal_ticket.id)
        print("internal_ticket.ticket_no =", internal_ticket.ticket_no)
        print("internal_ticket.status =", internal_ticket.status)
        print("internal_ticket.creator_id =", internal_ticket.creator_id)
        print("internal_ticket.external_session_id =", internal_ticket.external_session_id)
        print("internal_ticket.created_by_external =", internal_ticket.created_by_external)

        # ======================================================================
        # 14. 直接调用 AuditService 查看审计日志
        # ======================================================================
        print_line("14. 调用 AuditService.list_audit_logs(db, current_user, page, page_size)")

        audit_logs, audit_total = AuditService.list_audit_logs(
            db,
            current_user=current_user,
            page=1,
            page_size=20,
        )

        print("audit_total =", audit_total)
        for log in audit_logs:
            print(
                {
                    "id": str(log.id),
                    "user_id": str(log.user_id) if log.user_id else None,
                    "action": log.action,
                    "resource_type": log.resource_type,
                    "resource_id": log.resource_id,
                    "after_data": log.after_data,
                    "created_at": log.created_at,
                }
            )

    finally:
        db.close()


if __name__ == "__main__":
    main()