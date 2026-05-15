"""Repositories for Agent trace, pending action execution and RAG evidence.

Repository 层只负责数据库读写。
是否应该记录 succeeded / replayed / conflict，由 service 层根据业务流程决定。
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import utc_now
from app.models.agent_trace import (
    AgentToolCall,
    AgentToolCallStatus,
    PendingActionExecution,
    PendingActionExecutionStatus,
    TicketPolicyReference,
)


class PendingActionExecutionRepository:
    """pending_action_executions 表的数据访问对象。"""

    @staticmethod
    def create_received(
            db: Session,
            *,
            external_session_id: str,
            pending_action_id: str,
            idempotency_key: str,
            action_type: str,
            confirmed_by_external: str | None,
            confirmed_at: datetime | None,
    ) -> PendingActionExecution:
        """创建 received 状态记录，表示后端已经接收到这次业务动作。"""
        item = PendingActionExecution(
            external_session_id=external_session_id,
            pending_action_id=pending_action_id,
            idempotency_key=idempotency_key,
            action_type=action_type,
            status=PendingActionExecutionStatus.received,
            confirmed_by_external=confirmed_by_external,
            confirmed_at=confirmed_at,
        )
        db.add(item)
        db.flush()
        return item

    @staticmethod
    def mark_succeeded(
            db: Session,
            item: PendingActionExecution,
            *,
            result_resource_type: str,
            result_resource_id: str,
    ) -> PendingActionExecution:
        """标记 pending_action 首次执行成功。"""
        item.status = PendingActionExecutionStatus.succeeded
        item.executed_at = utc_now()
        item.result_resource_type = result_resource_type
        item.result_resource_id = result_resource_id
        db.add(item)
        db.flush()
        return item

    @staticmethod
    def mark_replayed(
            db: Session,
            item: PendingActionExecution,
            *,
            result_resource_type: str,
            result_resource_id: str,
    ) -> PendingActionExecution:
        """标记为幂等重放：没有创建新资源，而是复用已有资源。"""
        item.status = PendingActionExecutionStatus.idempotent_replayed
        item.executed_at = utc_now()
        item.result_resource_type = result_resource_type
        item.result_resource_id = result_resource_id
        db.add(item)
        db.flush()
        return item

    @staticmethod
    def mark_conflict(db: Session, item: PendingActionExecution, *, error_message: str) -> PendingActionExecution:
        """标记为幂等冲突。"""
        item.status = PendingActionExecutionStatus.conflict
        item.executed_at = utc_now()
        item.error_code = "IDEMPOTENCY_CONFLICT"
        item.error_message = error_message
        db.add(item)
        db.flush()
        return item

    @staticmethod
    def list_all(db: Session, *, offset: int, limit: int) -> tuple[list[PendingActionExecution], int]:
        """分页查询全部 pending_action 执行记录。"""
        total = db.scalar(select(func.count(PendingActionExecution.id))) or 0
        stmt = select(PendingActionExecution).order_by(PendingActionExecution.created_at.desc()).offset(offset).limit(
            limit)
        return list(db.scalars(stmt).all()), total

    @staticmethod
    def get_by_pending_action_id(db: Session, pending_action_id: str) -> PendingActionExecution | None:
        """查询某个 pending_action 最近一次执行记录。"""
        stmt = (
            select(PendingActionExecution)
            .where(PendingActionExecution.pending_action_id == pending_action_id)
            .order_by(PendingActionExecution.created_at.desc())
            .limit(1)
        )
        return db.scalar(stmt)


class AgentToolCallRepository:
    """agent_tool_calls 表的数据访问对象。"""

    @staticmethod
    def create_received(
            db: Session,
            *,
            trace_id: str,
            tool_call_id: str,
            external_session_id: str,
            pending_action_id: str,
            tool_name: str,
            request_payload: dict[str, Any],
    ) -> AgentToolCall:
        """创建 received 状态工具调用日志。"""
        item = AgentToolCall(
            trace_id=trace_id,
            tool_call_id=tool_call_id,
            external_session_id=external_session_id,
            pending_action_id=pending_action_id,
            tool_name=tool_name,
            request_payload=request_payload,
            status=AgentToolCallStatus.received,
        )
        db.add(item)
        db.flush()
        return item

    @staticmethod
    def mark_succeeded(
            db: Session,
            item: AgentToolCall,
            *,
            response_payload: dict[str, Any],
            latency_ms: int,
    ) -> AgentToolCall:
        """标记工具调用成功。"""
        item.status = AgentToolCallStatus.succeeded
        item.response_payload = response_payload
        item.latency_ms = latency_ms
        db.add(item)
        db.flush()
        return item

    @staticmethod
    def mark_replayed(
            db: Session,
            item: AgentToolCall,
            *,
            response_payload: dict[str, Any],
            latency_ms: int,
    ) -> AgentToolCall:
        """标记工具调用为 replayed，表示复用了幂等结果。"""
        item.status = AgentToolCallStatus.replayed
        item.response_payload = response_payload
        item.latency_ms = latency_ms
        db.add(item)
        db.flush()
        return item

    @staticmethod
    def mark_conflict(
            db: Session,
            item: AgentToolCall,
            *,
            error_message: str,
            latency_ms: int,
    ) -> AgentToolCall:
        """标记工具调用为 conflict。"""
        item.status = AgentToolCallStatus.conflict
        item.error_code = "IDEMPOTENCY_CONFLICT"
        item.error_message = error_message
        item.latency_ms = latency_ms
        db.add(item)
        db.flush()
        return item

    @staticmethod
    def list_all(db: Session, *, offset: int, limit: int) -> tuple[list[AgentToolCall], int]:
        """分页查询工具调用日志。"""
        total = db.scalar(select(func.count(AgentToolCall.id))) or 0
        stmt = select(AgentToolCall).order_by(AgentToolCall.created_at.desc()).offset(offset).limit(limit)
        return list(db.scalars(stmt).all()), total


class TicketPolicyReferenceRepository:
    """ticket_policy_references 表的数据访问对象。"""

    @staticmethod
    def create_many(
            db: Session,
            *,
            ticket_id: uuid.UUID,
            external_session_id: str | None,
            pending_action_id: str | None,
            rag_answer_snapshot: str | None,
            references: list[dict[str, Any]],
    ) -> list[TicketPolicyReference]:
        """批量保存 RAG sources 快照。"""
        items: list[TicketPolicyReference] = []
        for ref in references:
            item = TicketPolicyReference(
                ticket_id=ticket_id,
                external_session_id=external_session_id,
                pending_action_id=pending_action_id,
                rag_query=ref.get("rag_query"),
                rag_answer_snapshot=rag_answer_snapshot,
                document_id=ref.get("document_id"),
                document_name=ref.get("document_name"),
                chunk_id=ref.get("chunk_id"),
                breadcrumb=ref.get("breadcrumb"),
                page_number=ref.get("page_number"),
                retrieval_score=ref.get("retrieval_score"),
                content_snapshot=ref.get("content_snapshot"),
            )
            db.add(item)
            items.append(item)
        db.flush()
        return items

    @staticmethod
    def list_by_ticket_id(db: Session, *, ticket_id: uuid.UUID) -> list[TicketPolicyReference]:
        """查询某张工单关联的 RAG 依据。"""
        stmt = (
            select(TicketPolicyReference)
            .where(TicketPolicyReference.ticket_id == ticket_id)
            .order_by(TicketPolicyReference.created_at.asc())
        )
        return list(db.scalars(stmt).all())
