"""Internal ticket service.

这个 service 专门处理 Agent / 外部服务通过 Internal API 创建真实 HR 工单的业务用例。

为什么单独拆出来：
- TicketService 面向普通登录用户、HR、admin 的工单业务。
- InternalTicketService 面向 Agent 服务调用，集中处理幂等、request_hash、Agent trace、RAG evidence、pending_action 执行记录。
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
from app.core.exceptions import ConflictException
from app.core.security import utc_now
from app.models.idempotency import IdempotencyKey, IdempotencyStatus
from app.models.ticket import Ticket, TicketStatus
from app.repositories.agent_trace_repo import (
    AgentToolCallRepository,
    PendingActionExecutionRepository,
    TicketPolicyReferenceRepository,
)
from app.repositories.audit_repo import AuditRepository
from app.repositories.idempotency_repo import IdempotencyRepository
from app.repositories.ticket_repo import TicketRepository
from app.schemas.ticket import InternalTicketCreate


class InternalTicketService:
    """Agent Internal API 创建真实工单的业务服务。"""

    @staticmethod
    def create_ticket_from_internal(db: Session, *, payload: InternalTicketCreate) -> Ticket:
        """Internal API 幂等创建工单主入口。

        主流程只保留业务编排：
        1. 计算 request_hash。
        2. 查询 idempotency_key。
        3. 如果 key 已存在：处理 replay / conflict。
        4. 如果 key 不存在：首次创建 ticket，并写入 trace / evidence / audit。
        """
        start_time = time.perf_counter()
        request_hash = InternalTicketService._stable_request_hash(payload)
        existing_key = IdempotencyRepository.get_by_key(db, payload.idempotency_key)

        if existing_key:
            return InternalTicketService._handle_existing_idempotency_record(
                db=db,
                payload=payload,
                existing_key=existing_key,
                request_hash=request_hash,
                start_time=start_time,
            )

        return InternalTicketService._create_first_time(
            db=db,
            payload=payload,
            request_hash=request_hash,
            start_time=start_time,
        )

    @staticmethod
    def _handle_existing_idempotency_record(
        db: Session,
        *,
        payload: InternalTicketCreate,
        existing_key: IdempotencyKey,
        request_hash: str,
        start_time: float,
    ) -> Ticket:
        """处理已经存在的 idempotency_key。"""
        if existing_key.request_hash != request_hash:
            return InternalTicketService._handle_conflict(db=db, payload=payload, start_time=start_time)

        if existing_key.status == IdempotencyStatus.succeeded:
            return InternalTicketService._handle_replay(db=db, payload=payload, start_time=start_time)

        raise ConflictException(message="Idempotent request is still processing. Please retry later.")

    @staticmethod
    def _handle_replay(db: Session, *, payload: InternalTicketCreate, start_time: float) -> Ticket:
        """处理幂等重放：不重复创建 ticket，返回已有 ticket，并记录 replayed。"""
        ticket = TicketRepository.get_by_idempotency_key(db, payload.idempotency_key)
        if not ticket:
            raise ConflictException(message="Idempotency record exists but related ticket was not found.")

        try:
            execution, tool_call = InternalTicketService._create_received_trace_records(db=db, payload=payload)
            response_body = InternalTicketService._internal_response_body(ticket)
            PendingActionExecutionRepository.mark_replayed(
                db,
                execution,
                result_resource_type="ticket",
                result_resource_id=str(ticket.id),
            )
            AgentToolCallRepository.mark_replayed(
                db,
                tool_call,
                response_payload=response_body,
                latency_ms=InternalTicketService._latency_ms(start_time),
            )
            db.commit()
        except Exception:
            db.rollback()
            raise

        db.refresh(ticket)
        return ticket

    @staticmethod
    def _handle_conflict(db: Session, *, payload: InternalTicketCreate, start_time: float) -> Ticket:
        """处理同 key 不同 payload 的幂等冲突。"""
        message = "Idempotency key was already used with a different request payload."
        try:
            execution, tool_call = InternalTicketService._create_received_trace_records(db=db, payload=payload)
            PendingActionExecutionRepository.mark_conflict(db, execution, error_message=message)
            AgentToolCallRepository.mark_conflict(
                db,
                tool_call,
                error_message=message,
                latency_ms=InternalTicketService._latency_ms(start_time),
            )
            db.commit()
        except Exception:
            # conflict trace 写失败不能掩盖原本的 409 语义。
            db.rollback()

        raise ConflictException(message=message)

    @staticmethod
    def _create_first_time(
        db: Session,
        *,
        payload: InternalTicketCreate,
        request_hash: str,
        start_time: float,
    ) -> Ticket:
        """首次执行 Internal API 创建工单。

        ticket、idempotency、trace、evidence、audit 属于同一个业务事实，
        因此尽量在同一个事务中提交，避免半成功状态。
        """
        settings = get_settings()
        expires_at = utc_now() + timedelta(hours=settings.idempotency_key_ttl_hours)

        try:
            idempotency_item = IdempotencyRepository.create_processing(
                db,
                key=payload.idempotency_key,
                request_hash=request_hash,
                expires_at=expires_at,
            )
            execution, tool_call = InternalTicketService._create_received_trace_records(db=db, payload=payload)
            ticket = InternalTicketService._create_ticket_resource(db=db, payload=payload)
            InternalTicketService._create_policy_references(db=db, ticket=ticket, payload=payload)
            InternalTicketService._create_audit_log(db=db, ticket=ticket)

            response_body = InternalTicketService._internal_response_body(ticket)
            InternalTicketService._mark_success(
                db=db,
                idempotency_item=idempotency_item,
                execution=execution,
                tool_call=tool_call,
                ticket=ticket,
                response_body=response_body,
                start_time=start_time,
            )

            db.commit()
            db.refresh(ticket)
            return ticket
        except IntegrityError as exc:
            db.rollback()
            return InternalTicketService._handle_integrity_error_after_rollback(
                db=db,
                payload=payload,
                request_hash=request_hash,
                exc=exc,
            )
        except Exception:
            db.rollback()
            raise

    @staticmethod
    def _handle_integrity_error_after_rollback(
        db: Session,
        *,
        payload: InternalTicketCreate,
        request_hash: str,
        exc: IntegrityError,
    ) -> Ticket:
        """处理并发写入导致的唯一约束冲突。"""
        existing_after_rollback = IdempotencyRepository.get_by_key(db, payload.idempotency_key)
        if existing_after_rollback and existing_after_rollback.request_hash == request_hash:
            ticket = TicketRepository.get_by_idempotency_key(db, payload.idempotency_key)
            if ticket:
                return ticket
        raise ConflictException(message="Idempotency or ticket number conflict. Please retry.") from exc

    @staticmethod
    def _create_received_trace_records(db: Session, *, payload: InternalTicketCreate):
        """创建 pending_action_execution 和 agent_tool_call 的 received 初始记录。"""
        execution = PendingActionExecutionRepository.create_received(
            db,
            external_session_id=payload.external_session_id,
            pending_action_id=payload.pending_action_id,
            idempotency_key=payload.idempotency_key,
            action_type="create_hr_ticket",
            confirmed_by_external=payload.confirmed_by_external,
            confirmed_at=payload.confirmed_at,
        )
        tool_call = AgentToolCallRepository.create_received(
            db,
            trace_id=InternalTicketService._effective_trace_id(payload),
            tool_call_id=InternalTicketService._effective_tool_call_id(payload),
            external_session_id=payload.external_session_id,
            pending_action_id=payload.pending_action_id,
            tool_name=payload.tool_name,
            request_payload=payload.model_dump(mode="json"),
        )
        return execution, tool_call

    @staticmethod
    def _create_ticket_resource(db: Session, *, payload: InternalTicketCreate) -> Ticket:
        """创建真实 Ticket 业务资源。"""
        return TicketRepository.create(
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

    @staticmethod
    def _create_policy_references(db: Session, *, ticket: Ticket, payload: InternalTicketCreate) -> None:
        """保存 RAG sources / 企业制度依据快照。"""
        references = [item.model_dump(mode="json") for item in payload.rag_references]
        if not references:
            return
        TicketPolicyReferenceRepository.create_many(
            db,
            ticket_id=ticket.id,
            external_session_id=payload.external_session_id,
            pending_action_id=payload.pending_action_id,
            rag_answer_snapshot=payload.rag_answer_snapshot,
            references=references,
        )

    @staticmethod
    def _create_audit_log(db: Session, *, ticket: Ticket) -> None:
        """写入业务审计日志。"""
        AuditRepository.create(
            db,
            user_id=None,
            action="ticket.created_by_internal_api",
            resource_type="ticket",
            resource_id=str(ticket.id),
            before_data=None,
            after_data=InternalTicketService._ticket_audit_data(ticket),
        )

    @staticmethod
    def _mark_success(
        db: Session,
        *,
        idempotency_item: IdempotencyKey,
        execution,
        tool_call,
        ticket: Ticket,
        response_body: dict[str, Any],
        start_time: float,
    ) -> None:
        """统一标记首次执行成功。"""
        IdempotencyRepository.mark_succeeded(
            db,
            idempotency_item,
            resource_type="ticket",
            resource_id=str(ticket.id),
            response_body=response_body,
        )
        PendingActionExecutionRepository.mark_succeeded(
            db,
            execution,
            result_resource_type="ticket",
            result_resource_id=str(ticket.id),
        )
        AgentToolCallRepository.mark_succeeded(
            db,
            tool_call,
            response_payload=response_body,
            latency_ms=InternalTicketService._latency_ms(start_time),
        )

    @staticmethod
    def _stable_request_hash(payload: InternalTicketCreate) -> str:
        """计算 Internal API 请求体稳定哈希。"""
        data = payload.model_dump(
            mode="json",
            exclude={"idempotency_key", "trace_id", "tool_call_id", "tool_name", "agent_trace"},
        )
        raw = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _effective_trace_id(payload: InternalTicketCreate) -> str:
        return payload.trace_id or f"trace-{uuid.uuid4().hex}"

    @staticmethod
    def _effective_tool_call_id(payload: InternalTicketCreate) -> str:
        return payload.tool_call_id or f"tool-call-{uuid.uuid4().hex}"

    @staticmethod
    def _latency_ms(start_time: float) -> int:
        return int((time.perf_counter() - start_time) * 1000)

    @staticmethod
    def _ticket_audit_data(ticket: Ticket) -> dict[str, Any]:
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

    @staticmethod
    def _internal_response_body(ticket: Ticket) -> dict[str, Any]:
        return {
            "id": str(ticket.id),
            "ticket_no": ticket.ticket_no,
            "ticket_type": ticket.ticket_type.value,
            "title": ticket.title,
            "status": ticket.status.value,
            "pending_action_id": ticket.pending_action_id,
            "idempotency_key": ticket.idempotency_key,
        }
