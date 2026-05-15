"""Ticket business service.

第四阶段后，TicketService 专注普通用户 / HR / admin 的工单业务：
- 登录用户创建工单
- 按权限查询工单
- 工单状态机
- 分配处理人
- 取消工单
- 查询状态流转历史

Agent Internal API 创建工单的复杂逻辑已经拆到 InternalTicketService。
"""

import uuid
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictException, ForbiddenException, NotFoundException
from app.core.permissions import can_view_all_tickets, can_view_ticket
from app.models.ticket import Ticket, TicketStatus
from app.models.user import User, UserRole
from app.repositories.agent_trace_repo import TicketPolicyReferenceRepository
from app.repositories.audit_repo import AuditRepository
from app.repositories.ticket_repo import TicketRepository
from app.repositories.ticket_transition_repo import TicketStatusTransitionRepository
from app.repositories.user_repo import UserRepository
from app.schemas.ticket import InternalTicketCreate, TicketCreate
from app.schemas.ticket_transition import TicketAssignRequest, TicketCancelRequest, TicketStatusUpdate


# 状态机只定义合法边，不把权限写在这里。
# 权限由 _ensure_status_transition_permission 单独判断。
ALLOWED_STATUS_TRANSITIONS: set[tuple[TicketStatus, TicketStatus]] = {
    (TicketStatus.open, TicketStatus.processing),
    (TicketStatus.processing, TicketStatus.resolved),
    (TicketStatus.resolved, TicketStatus.closed),
    (TicketStatus.open, TicketStatus.cancelled),
}


TERMINAL_STATUSES = {TicketStatus.closed, TicketStatus.cancelled}


def _ticket_audit_data(ticket: Ticket) -> dict[str, Any]:
    """把 Ticket ORM 对象转成可存入 audit_logs 的 JSON 快照。"""
    return {
        "id": str(ticket.id),
        "ticket_no": ticket.ticket_no,
        "ticket_type": ticket.ticket_type.value,
        "title": ticket.title,
        "status": ticket.status.value,
        "priority": ticket.priority.value,
        "creator_id": str(ticket.creator_id) if ticket.creator_id else None,
        "assignee_id": str(ticket.assignee_id) if ticket.assignee_id else None,
        "external_session_id": ticket.external_session_id,
        "pending_action_id": ticket.pending_action_id,
        "idempotency_key": ticket.idempotency_key,
        "created_by_external": ticket.created_by_external,
    }


class TicketService:
    """工单业务服务。"""

    @staticmethod
    def create_ticket_for_user(db: Session, *, payload: TicketCreate, creator: User) -> Ticket:
        """登录用户创建自己的工单。"""
        try:
            ticket = TicketRepository.create(
                db,
                ticket_no=TicketRepository.generate_ticket_no(db),
                ticket_type=payload.ticket_type,
                title=payload.title,
                description=payload.description,
                priority=payload.priority,
                status=TicketStatus.open,
                creator_id=creator.id,
            )
            AuditRepository.create(
                db,
                user_id=creator.id,
                action="ticket.created",
                resource_type="ticket",
                resource_id=str(ticket.id),
                before_data=None,
                after_data=_ticket_audit_data(ticket),
            )
            db.commit()
            db.refresh(ticket)
            return ticket
        except IntegrityError as exc:
            db.rollback()
            raise ConflictException(message="Ticket number conflict. Please retry.") from exc
        except Exception:
            db.rollback()
            raise

    @staticmethod
    def create_ticket_from_internal(db: Session, *, payload: InternalTicketCreate) -> Ticket:
        """兼容旧调用入口。

        Internal API 创建工单已经迁移到 InternalTicketService。
        这里保留代理方法，避免旧测试或旧调用路径失效。
        """
        from app.services.internal_ticket_service import InternalTicketService

        return InternalTicketService.create_ticket_from_internal(db=db, payload=payload)

    @staticmethod
    def list_tickets(db: Session, *, current_user: User, page: int, page_size: int) -> tuple[list[Ticket], int]:
        """按当前用户权限查询工单列表。"""
        offset = (page - 1) * page_size
        if can_view_all_tickets(current_user):
            return TicketRepository.list_all(db, offset=offset, limit=page_size)
        return TicketRepository.list_by_creator(db, creator_id=current_user.id, offset=offset, limit=page_size)

    @staticmethod
    def get_ticket(db: Session, *, ticket_id: uuid.UUID, current_user: User) -> Ticket:
        """查询工单详情，并进行资源级权限判断。"""
        ticket = TicketRepository.get_by_id(db, ticket_id)
        if not ticket:
            raise NotFoundException(message="Ticket not found.")
        if not can_view_ticket(current_user, ticket.creator_id):
            raise ForbiddenException(message="You do not have permission to access this ticket.")
        return ticket

    @staticmethod
    def update_status(
        db: Session,
        *,
        ticket_id: uuid.UUID,
        payload: TicketStatusUpdate,
        current_user: User,
    ) -> Ticket:
        """按轻量状态机更新工单状态。

        关键原则：
        - 不能任意修改 status，必须符合状态机合法边。
        - 权限判断要结合角色、资源归属和当前状态。
        - ticket.status 更新、transition 记录、audit_log 应在同一事务中提交。
        """
        ticket = TicketService.get_ticket(db, ticket_id=ticket_id, current_user=current_user)
        from_status = ticket.status
        to_status = payload.status

        TicketService._ensure_status_transition_allowed(from_status, to_status)
        TicketService._ensure_status_transition_permission(
            ticket=ticket,
            current_user=current_user,
            from_status=from_status,
            to_status=to_status,
        )

        before_data = _ticket_audit_data(ticket)
        try:
            ticket.status = to_status
            TicketStatusTransitionRepository.create(
                db,
                ticket_id=ticket.id,
                from_status=from_status,
                to_status=to_status,
                operator_id=current_user.id,
                operator_role=current_user.role,
                reason=payload.reason,
            )
            AuditRepository.create(
                db,
                user_id=current_user.id,
                action="ticket.status_changed",
                resource_type="ticket",
                resource_id=str(ticket.id),
                before_data=before_data,
                after_data=_ticket_audit_data(ticket),
            )
            db.commit()
            db.refresh(ticket)
            return ticket
        except Exception:
            db.rollback()
            raise

    @staticmethod
    def assign_ticket(
        db: Session,
        *,
        ticket_id: uuid.UUID,
        payload: TicketAssignRequest,
        current_user: User,
    ) -> Ticket:
        """HR / admin 分配工单处理人。"""
        if current_user.role not in {UserRole.hr, UserRole.admin}:
            raise ForbiddenException(message="Only hr or admin can assign tickets.")

        ticket = TicketService.get_ticket(db, ticket_id=ticket_id, current_user=current_user)
        if ticket.status in TERMINAL_STATUSES:
            raise ConflictException(message="Closed or cancelled ticket cannot be assigned.")

        assignee = UserRepository.get_by_id(db, payload.assignee_id)
        if not assignee or not assignee.is_active:
            raise NotFoundException(message="Assignee not found or inactive.")
        if assignee.role not in {UserRole.hr, UserRole.admin}:
            raise ForbiddenException(message="Assignee must be hr or admin.")

        before_data = _ticket_audit_data(ticket)
        try:
            ticket.assignee_id = assignee.id
            AuditRepository.create(
                db,
                user_id=current_user.id,
                action="ticket.assigned",
                resource_type="ticket",
                resource_id=str(ticket.id),
                before_data=before_data,
                after_data=_ticket_audit_data(ticket) | {"assign_reason": payload.reason},
            )
            db.commit()
            db.refresh(ticket)
            return ticket
        except Exception:
            db.rollback()
            raise

    @staticmethod
    def cancel_ticket(
        db: Session,
        *,
        ticket_id: uuid.UUID,
        payload: TicketCancelRequest,
        current_user: User,
    ) -> Ticket:
        """取消工单。

        employee 只能取消自己 open 状态的工单；hr/admin 可以取消任意 open 工单。
        """
        ticket = TicketService.get_ticket(db, ticket_id=ticket_id, current_user=current_user)
        from_status = ticket.status
        to_status = TicketStatus.cancelled

        TicketService._ensure_status_transition_allowed(from_status, to_status)
        TicketService._ensure_cancel_permission(ticket=ticket, current_user=current_user)

        before_data = _ticket_audit_data(ticket)
        try:
            ticket.status = to_status
            TicketStatusTransitionRepository.create(
                db,
                ticket_id=ticket.id,
                from_status=from_status,
                to_status=to_status,
                operator_id=current_user.id,
                operator_role=current_user.role,
                reason=payload.reason,
            )
            AuditRepository.create(
                db,
                user_id=current_user.id,
                action="ticket.cancelled",
                resource_type="ticket",
                resource_id=str(ticket.id),
                before_data=before_data,
                after_data=_ticket_audit_data(ticket),
            )
            db.commit()
            db.refresh(ticket)
            return ticket
        except Exception:
            db.rollback()
            raise

    @staticmethod
    def list_transitions(db: Session, *, ticket_id: uuid.UUID, current_user: User):
        """查询某张工单状态流转历史，权限沿用工单详情。"""
        ticket = TicketService.get_ticket(db, ticket_id=ticket_id, current_user=current_user)
        return TicketStatusTransitionRepository.list_by_ticket_id(db, ticket_id=ticket.id)

    @staticmethod
    def list_policy_references(db: Session, *, ticket_id: uuid.UUID, current_user: User):
        """查询某张工单的 RAG evidence。"""
        ticket = TicketService.get_ticket(db, ticket_id=ticket_id, current_user=current_user)
        return TicketPolicyReferenceRepository.list_by_ticket_id(db, ticket_id=ticket.id)

    @staticmethod
    def _ensure_status_transition_allowed(from_status: TicketStatus, to_status: TicketStatus) -> None:
        """校验状态机合法边。"""
        if from_status == to_status:
            raise ConflictException(message="Ticket is already in the target status.")
        if from_status in TERMINAL_STATUSES:
            raise ConflictException(message="Closed or cancelled ticket cannot be changed.")
        if (from_status, to_status) not in ALLOWED_STATUS_TRANSITIONS:
            raise ConflictException(message=f"Invalid ticket status transition: {from_status.value} -> {to_status.value}.")

    @staticmethod
    def _ensure_status_transition_permission(
        *,
        ticket: Ticket,
        current_user: User,
        from_status: TicketStatus,
        to_status: TicketStatus,
    ) -> None:
        """校验不同角色在不同状态下能否执行目标流转。"""
        if current_user.role == UserRole.admin:
            return

        if current_user.role == UserRole.hr:
            if (from_status, to_status) in {
                (TicketStatus.open, TicketStatus.processing),
                (TicketStatus.processing, TicketStatus.resolved),
                (TicketStatus.resolved, TicketStatus.closed),
            }:
                return
            raise ForbiddenException(message="HR cannot perform this ticket status transition.")

        # employee 只允许关闭自己已经 resolved 的工单。
        if current_user.role == UserRole.employee:
            if ticket.creator_id == current_user.id and (from_status, to_status) == (TicketStatus.resolved, TicketStatus.closed):
                return
            raise ForbiddenException(message="Employee cannot perform this ticket status transition.")

        raise ForbiddenException(message="You do not have permission to update ticket status.")

    @staticmethod
    def _ensure_cancel_permission(*, ticket: Ticket, current_user: User) -> None:
        """校验取消权限。"""
        if ticket.status != TicketStatus.open:
            raise ConflictException(message="Only open tickets can be cancelled.")
        if current_user.role in {UserRole.hr, UserRole.admin}:
            return
        if ticket.creator_id == current_user.id:
            return
        raise ForbiddenException(message="You can only cancel your own open tickets.")
