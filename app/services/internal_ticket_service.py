"""Internal ticket service.

这个 service 专门处理 Agent / 外部服务通过 Internal API 创建真实 HR 工单的业务用例。

为什么单独拆出来：
- TicketService 主要面向普通登录用户、HR、admin 的工单业务。
- InternalTicketService 面向 Agent 服务调用，逻辑更复杂：
  1. 幂等检查
  2. request_hash 校验
  3. replay / conflict 处理
  4. pending_action_execution 落库
  5. agent_tool_call 落库
  6. RAG evidence 落库
  7. audit_log 落库
  8. 事务一致性控制

Router 不应该承担这些业务判断；Repository 也不应该承担业务判断。
因此这里作为 Internal API 创建工单的应用服务层。
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

        注意：
        - API Key 校验不在这里做，由 router/deps 层负责。
        - JWT 鉴权不在这里做，Internal API 是服务间调用。
        - Repository 只负责数据库读写，业务判断放在 service 层。
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

    # -------------------------------------------------------------------------
    # 幂等请求分流
    # -------------------------------------------------------------------------

    @staticmethod
    def _handle_existing_idempotency_record(
        db: Session,
        *,
        payload: InternalTicketCreate,
        existing_key: IdempotencyKey,
        request_hash: str,
        start_time: float,
    ) -> Ticket:
        """处理已经存在的 idempotency_key。

        三种情况：
        1. 同 key + 不同 request_hash：冲突，拒绝。
        2. 同 key + 同 request_hash + succeeded：幂等重放，返回已有 ticket。
        3. 同 key + 同 request_hash + processing/failed：当前版本返回冲突。
        """
        if existing_key.request_hash != request_hash:
            return InternalTicketService._handle_conflict(
                db=db,
                payload=payload,
                start_time=start_time,
            )

        if existing_key.status == IdempotencyStatus.succeeded:
            return InternalTicketService._handle_replay(
                db=db,
                payload=payload,
                start_time=start_time,
            )

        raise ConflictException(message="Idempotent request is still processing. Please retry later.")

    @staticmethod
    def _handle_replay(
        db: Session,
        *,
        payload: InternalTicketCreate,
        start_time: float,
    ) -> Ticket:
        """处理幂等重放。

        replay 不是错误。它表示：
        - Agent 或上游服务重复发送了同一个业务动作。
        - 后端已经创建过 ticket。
        - 本次不再创建新 ticket，只返回已有 ticket。

        但 replay 仍然要记录：
        - pending_action_execution = idempotent_replayed
        - agent_tool_call = replayed

        这样后续可以看出某个 pending_action 被重复调用过。
        """
        ticket = TicketRepository.get_by_idempotency_key(db, payload.idempotency_key)
        if not ticket:
            raise ConflictException(message="Idempotency record exists but related ticket was not found.")

        try:
            execution, tool_call = InternalTicketService._create_received_trace_records(
                db=db,
                payload=payload,
            )
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
    def _handle_conflict(
        db: Session,
        *,
        payload: InternalTicketCreate,
        start_time: float,
    ) -> Ticket:
        """处理幂等冲突。

        冲突条件：
        - idempotency_key 相同
        - request_hash 不同

        这说明调用方复用了同一个 key，但业务 payload 发生变化。
        这种情况不能覆盖旧资源，也不能默默返回旧资源，必须拒绝。
        """
        message = "Idempotency key was already used with a different request payload."

        try:
            execution, tool_call = InternalTicketService._create_received_trace_records(
                db=db,
                payload=payload,
            )

            PendingActionExecutionRepository.mark_conflict(
                db,
                execution,
                error_message=message,
            )
            AgentToolCallRepository.mark_conflict(
                db,
                tool_call,
                error_message=message,
                latency_ms=InternalTicketService._latency_ms(start_time),
            )

            db.commit()
        except Exception:
            # conflict trace 写失败不应该掩盖原本的 409 语义。
            # 这里回滚后仍然抛出 ConflictException。
            db.rollback()

        raise ConflictException(message=message)

    # -------------------------------------------------------------------------
    # 首次创建完整流程
    # -------------------------------------------------------------------------

    @staticmethod
    def _create_first_time(
        db: Session,
        *,
        payload: InternalTicketCreate,
        request_hash: str,
        start_time: float,
    ) -> Ticket:
        """首次执行 Internal API 创建工单。

        这一组写操作必须保持事务一致：
        - idempotency_keys
        - pending_action_executions
        - agent_tool_calls
        - tickets
        - ticket_policy_references
        - audit_logs

        要么一起成功，要么一起回滚。
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

            execution, tool_call = InternalTicketService._create_received_trace_records(
                db=db,
                payload=payload,
            )

            ticket = InternalTicketService._create_ticket_resource(
                db=db,
                payload=payload,
            )

            InternalTicketService._create_policy_references(
                db=db,
                ticket=ticket,
                payload=payload,
            )

            InternalTicketService._create_audit_log(
                db=db,
                ticket=ticket,
            )

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
        """处理并发写入导致的唯一约束冲突。

        典型场景：
        两个请求几乎同时使用同一个 idempotency_key 进来。
        其中一个成功创建，另一个在插入 idempotency_keys 时触发唯一约束冲突。

        回滚后再次查询：
        - 如果已经存在相同 key + 相同 hash，并且 ticket 已创建，则返回已有 ticket。
        - 否则抛出 409。
        """
        existing_after_rollback = IdempotencyRepository.get_by_key(db, payload.idempotency_key)

        if existing_after_rollback and existing_after_rollback.request_hash == request_hash:
            ticket = TicketRepository.get_by_idempotency_key(db, payload.idempotency_key)
            if ticket:
                return ticket

        raise ConflictException(message="Idempotency or ticket number conflict. Please retry.") from exc

    # -------------------------------------------------------------------------
    # 创建子资源
    # -------------------------------------------------------------------------

    @staticmethod
    def _create_received_trace_records(
        db: Session,
        *,
        payload: InternalTicketCreate,
    ):
        """创建 pending_action_execution 和 agent_tool_call 初始记录。

        初始状态都是 received，表示后端已经接收到这次 Agent 工具调用。
        """
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
            request_payload=InternalTicketService._tool_call_request_payload(payload),
        )

        return execution, tool_call

    @staticmethod
    def _create_ticket_resource(
        db: Session,
        *,
        payload: InternalTicketCreate,
    ) -> Ticket:
        """创建真实 Ticket 业务资源。

        这里只负责 ticket 本身，不处理幂等、trace、audit、RAG evidence。
        """
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
    def _create_policy_references(
        db: Session,
        *,
        ticket: Ticket,
        payload: InternalTicketCreate,
    ) -> None:
        """保存 RAG sources / 企业制度依据快照。

        注意：
        - 这里不是重新实现 RAG。
        - 这里只保存 Agent 调用 RAG 后传来的 sources 快照。
        - 即使后续知识库更新，历史工单仍然可以解释当时依据。
        """
        reference_payloads = [item.model_dump(mode="json") for item in payload.rag_references]
        if not reference_payloads:
            return

        TicketPolicyReferenceRepository.create_many(
            db,
            ticket_id=ticket.id,
            external_session_id=payload.external_session_id,
            pending_action_id=payload.pending_action_id,
            rag_answer_snapshot=payload.rag_answer_snapshot,
            references=reference_payloads,
        )

    @staticmethod
    def _create_audit_log(
        db: Session,
        *,
        ticket: Ticket,
    ) -> None:
        """写入业务审计日志。

        audit_logs 记录的是业务事实：
        “后端通过 Internal API 创建了一张真实 ticket。”
        """
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
        """统一标记首次执行成功。

        同一个业务用例成功时，需要同时更新：
        - idempotency_keys = succeeded
        - pending_action_executions = succeeded
        - agent_tool_calls = succeeded
        """
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

    # -------------------------------------------------------------------------
    # 工具方法
    # -------------------------------------------------------------------------

    @staticmethod
    def _stable_request_hash(payload: InternalTicketCreate) -> str:
        """计算 Internal API 请求体稳定哈希。

        设计重点：
        - idempotency_key 不参与哈希，因为它是幂等身份本身。
        - trace_id / tool_call_id / tool_name / agent_trace 不参与哈希，
          因为 Agent 重试时这些追踪字段可能变化，但业务动作仍是同一次。
        - ticket 字段、pending_action_id、RAG evidence 参与哈希，
          用于防止同 key 下业务内容变化。
        """
        data = payload.model_dump(
            mode="json",
            exclude={
                "idempotency_key",
                "trace_id",
                "tool_call_id",
                "tool_name",
                "agent_trace",
            },
        )
        raw = json.dumps(
            data,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _effective_trace_id(payload: InternalTicketCreate) -> str:
        """Agent 没传 trace_id 时，由后端生成一个可追踪 ID。"""
        return payload.trace_id or f"trace-{uuid.uuid4().hex}"

    @staticmethod
    def _effective_tool_call_id(payload: InternalTicketCreate) -> str:
        """Agent 没传 tool_call_id 时，由后端生成一个可追踪 ID。"""
        return payload.tool_call_id or f"tool-call-{uuid.uuid4().hex}"

    @staticmethod
    def _tool_call_request_payload(payload: InternalTicketCreate) -> dict[str, Any]:
        """生成 agent_tool_calls.request_payload 快照。

        request_payload 保存 Agent 调用上下文，不只保存 ticket 字段。
        """
        return payload.model_dump(mode="json")

    @staticmethod
    def _latency_ms(start_time: float) -> int:
        """计算工具调用耗时，单位毫秒。"""
        return int((time.perf_counter() - start_time) * 1000)

    @staticmethod
    def _ticket_audit_data(ticket: Ticket) -> dict[str, Any]:
        """把 Ticket ORM 对象转成 audit_logs.after_data JSON 快照。"""
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
        """生成 Internal API 响应快照。

        这个快照会同时写入：
        - idempotency_keys.response_body
        - agent_tool_calls.response_payload
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