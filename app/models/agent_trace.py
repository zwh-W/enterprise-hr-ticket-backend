"""Agent trace related ORM models.

第三阶段核心目标：把 Agent 调用后端的关键链路落库。
这些表不是普通业务表，而是 AI 应用工程里的可观测性和可解释性数据。

三张表的职责：
- PendingActionExecution：记录某个 pending_action 在后端是否被执行。
- AgentToolCall：记录 Agent 调用了什么工具、传了什么参数、返回了什么。
- TicketPolicyReference：记录某张工单依据了哪些 RAG sources / 制度 chunk。
"""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.security import utc_now
from app.db.base import Base


class PendingActionExecutionStatus(str, enum.Enum):
    """pending_action 在后端执行层的状态。

    received：后端已经接收并准备执行。
    succeeded：首次执行成功，并生成真实业务资源。
    failed：执行失败。当前版本主要预留给后续更复杂的失败补偿。
    idempotent_replayed：同一个幂等请求重复到达，后端复用已有结果。
    conflict：同一幂等键下请求体发生变化，后端拒绝执行。
    """

    received = "received"
    succeeded = "succeeded"
    failed = "failed"
    idempotent_replayed = "idempotent_replayed"
    conflict = "conflict"


class AgentToolCallStatus(str, enum.Enum):
    """Agent tool call 的处理状态。"""

    received = "received"
    succeeded = "succeeded"
    failed = "failed"
    replayed = "replayed"
    conflict = "conflict"


class PendingActionExecution(Base):
    """pending_action 执行记录表。

    它回答的问题是：
    “Agent 生成并由用户确认的那个 pending_action，后端到底有没有执行？执行结果是什么？”

    注意：它不是幂等表。幂等表关注“请求是否重复执行”；
    pending_action_executions 关注“业务动作执行过程与结果”。
    """

    __tablename__ = "pending_action_executions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)

    external_session_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    pending_action_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), index=True, nullable=False)

    action_type: Mapped[str] = mapped_column(String(100), nullable=False, default="create_hr_ticket")
    status: Mapped[PendingActionExecutionStatus] = mapped_column(
        Enum(PendingActionExecutionStatus, name="pending_action_execution_status", native_enum=False),
        nullable=False,
        default=PendingActionExecutionStatus.received,
        index=True,
    )

    # 用户确认信息来自 Agent 服务。Backend 不直接管理 Agent 侧用户体系，所以保存 external 表示。
    confirmed_by_external: Mapped[str | None] = mapped_column(String(128), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # 执行成功后的业务资源引用。当前主要是 ticket。
    result_resource_type: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    result_resource_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)

    # 失败 / 冲突时记录标准错误信息，便于 Agent 给用户生成可理解反馈。
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )


class AgentToolCall(Base):
    """Agent 工具调用日志表。

    它回答的问题是：
    “Agent 调了哪个工具？请求参数是什么？后端返回什么？耗时多少？是否失败？”

    它和 audit_logs 的区别：
    - audit_logs 记录业务资源发生了什么变化。
    - agent_tool_calls 记录 AI 工具调用过程。
    """

    __tablename__ = "agent_tool_calls"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)

    trace_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    tool_call_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    external_session_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    pending_action_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)

    tool_name: Mapped[str] = mapped_column(String(100), nullable=False, default="create_hr_ticket")

    # JSON 字段保存 Agent 调用参数与后端响应快照。后续排查时可以还原当时调用现场。
    request_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    response_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    status: Mapped[AgentToolCallStatus] = mapped_column(
        Enum(AgentToolCallStatus, name="agent_tool_call_status", native_enum=False),
        nullable=False,
        default=AgentToolCallStatus.received,
        index=True,
    )
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )


class TicketPolicyReference(Base):
    """工单关联的 RAG 制度依据表。

    它回答的问题是：
    “Agent 创建这个 HR 工单时，依据了哪些制度文档和 chunk？”

    这不是 RAG 系统本身；它只是把 RAG 当时返回的关键 sources 做业务快照。
    这样即使之后知识库内容变化，仍然能解释当时为什么创建该工单。
    """

    __tablename__ = "ticket_policy_references"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)

    ticket_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tickets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    external_session_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    pending_action_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)

    rag_query: Mapped[str | None] = mapped_column(Text, nullable=True)
    rag_answer_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)

    document_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    document_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    chunk_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    breadcrumb: Mapped[str | None] = mapped_column(String(500), nullable=True)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retrieval_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # 保存 chunk 原文快照，避免后续知识库更新后无法解释历史工单。
    content_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
