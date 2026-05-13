"""Ticket business service.

Service 层负责业务规则：权限、事务边界、审计日志、幂等处理。
Repository 层只做数据库访问，不承担业务判断。
"""

import hashlib
import json
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


def _internal_response_body(ticket: Ticket) -> dict[str, Any]:
    """生成 Internal API 响应快照。

    这个快照会写入 idempotency_keys.response_body，方便后续排查和复用。
    """
    return {
        "id": str(ticket.id),
        "ticket_no": ticket.ticket_no,
        "ticket_type": ticket.ticket_type.value,
        "title": ticket.title,
        "status": ticket.status.value,
        "pending_action_id": ticket.pending_action_id,
        "idempotency_key": ticket.idempotency_key,
    }


def _stable_request_hash(payload: InternalTicketCreate) -> str:
    """计算 Internal API 请求体的稳定哈希。

    注意：故意排除 idempotency_key 本身。
    因为我们要判断“同一个 key 对应的业务请求是否相同”。
    如果 title / description / pending_action_id 等任一业务字段变化，哈希就会变化。
    """
    data = payload.model_dump(mode="json", exclude={"idempotency_key"})
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


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
        """Internal API 幂等创建工单。
        幂等保护的工单创建业务

        核心规则：
        1. 相同 idempotency_key + 相同请求体：返回已创建的同一个 ticket。
        2. 相同 idempotency_key + 不同请求体：返回 409，拒绝复用 key。
        3. 新 idempotency_key：创建幂等记录、创建 ticket、写审计日志、提交事务。
        """
        request_hash = _stable_request_hash(payload)

        existing_key = IdempotencyRepository.get_by_key(db, payload.idempotency_key)
        if existing_key:
            if existing_key.request_hash != request_hash:
                raise ConflictException(message="Idempotency key was already used with a different request payload.")

            if existing_key.status == IdempotencyStatus.succeeded:
                ticket = TicketRepository.get_by_idempotency_key(db, payload.idempotency_key)
                if ticket:
                    return ticket
                raise ConflictException(message="Idempotency record exists but related ticket was not found.")

            raise ConflictException(message="Idempotent request is still processing. Please retry later.")

        settings = get_settings()
        expires_at = utc_now() + timedelta(hours=settings.idempotency_key_ttl_hours)

        try:
            idempotency_item = IdempotencyRepository.create_processing(
                db,
                key=payload.idempotency_key,
                request_hash=request_hash,
                expires_at=expires_at,
            )

            ticket = TicketRepository.create(
                db,
                ticket_no=TicketRepository.generate_ticket_no(db),
                ticket_type=payload.ticket_type,
                title=payload.title,
                description=payload.description,
                priority=payload.priority,
                status=TicketStatus.open,
                creator_id=None,
                external_session_id=payload.external_session_id,
                pending_action_id=payload.pending_action_id,
                idempotency_key=payload.idempotency_key,
                created_by_external=payload.created_by_external,
            )

            AuditRepository.create(
                db,
                user_id=None,
                action="ticket.created_by_internal_api",
                resource_type="ticket",
                resource_id=str(ticket.id),
                before_data=None,
                after_data=_ticket_audit_data(ticket),
            )

            IdempotencyRepository.mark_succeeded(
                db,
                idempotency_item,
                resource_type="ticket",
                resource_id=str(ticket.id),
                response_body=_internal_response_body(ticket),
            )

            db.commit()
            db.refresh(ticket)
            return ticket
        except IntegrityError as exc:
            db.rollback()

            # 如果并发请求刚好抢同一个 key，回滚后再读一次已有结果。
            # 这不是完整分布式并发方案，但能覆盖基础重试场景。
            existing_after_rollback = IdempotencyRepository.get_by_key(db, payload.idempotency_key)
            if existing_after_rollback and existing_after_rollback.request_hash == request_hash:
                ticket = TicketRepository.get_by_idempotency_key(db, payload.idempotency_key)
                if ticket:
                    return ticket

            raise ConflictException(message="Idempotency or ticket number conflict. Please retry.") from exc
        except Exception:
            db.rollback()
            raise

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
