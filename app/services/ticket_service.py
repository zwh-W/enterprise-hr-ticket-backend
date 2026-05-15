"""Ticket business service.

Service 层负责业务规则：权限、事务边界、审计日志、幂等处理、Agent trace 落库、RAG evidence 落库。
Repository 层只做数据库访问，不承担业务判断。
"""

import hashlib
import json
import time
import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import ConflictException, ForbiddenException, NotFoundException
from app.core.permissions import can_view_all_tickets, can_view_ticket
from app.core.security import utc_now
from app.models.idempotency import IdempotencyStatus
from app.models.ticket import Ticket, TicketStatus
from app.models.user import User
from app.repositories.agent_trace_repo import (
    AgentToolCallRepository,
    PendingActionExecutionRepository,
    TicketPolicyReferenceRepository,
)
from app.repositories.audit_repo import AuditRepository
from app.repositories.idempotency_repo import IdempotencyRepository
from app.repositories.ticket_repo import TicketRepository
from app.schemas.ticket import InternalTicketCreate, TicketCreate


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

        第三阶段后，Internal API 创建工单逻辑已经迁移到
        InternalTicketService。

        保留这个代理方法的作用：
        - 旧测试不会马上失效。
        - 后续如果还有代码调用 TicketService.create_ticket_from_internal，
          仍然可以正常工作。
        """
        from app.services.internal_ticket_service import InternalTicketService

        return InternalTicketService.create_ticket_from_internal(
            db=db,
            payload=payload,
        )


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
    def list_policy_references(db: Session, *, ticket_id: uuid.UUID, current_user: User):
        """查询某张工单的 RAG evidence。

        权限沿用工单详情权限：员工只能看自己工单的依据，hr/admin 可看全部。
        """
        ticket = TicketService.get_ticket(db, ticket_id=ticket_id, current_user=current_user)
        return TicketPolicyReferenceRepository.list_by_ticket_id(db, ticket_id=ticket.id)
