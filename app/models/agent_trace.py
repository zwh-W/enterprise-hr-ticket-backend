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

    # 主键唯一ID
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # 外部会话ID，关联用户对话上下文
    external_session_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False, comment="外部会话ID")

    # Agent 侧生成的待执行动作ID，用于追踪业务动作
    pending_action_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False, comment="待执行动作ID")

    # 幂等键，防止同一个动作被重复执行
    idempotency_key: Mapped[str] = mapped_column(String(255), index=True, nullable=False, comment="幂等键，防重复执行")

    # 动作类型，默认创建HR工单
    action_type: Mapped[str] = mapped_column(String(100), nullable=False, default="create_hr_ticket",
                                             comment="动作类型")

    # 动作执行状态（已接收/成功/失败/重复/冲突）
    status: Mapped[PendingActionExecutionStatus] = mapped_column(
        Enum(PendingActionExecutionStatus, name="pending_action_execution_status", native_enum=False),
        nullable=False,
        default=PendingActionExecutionStatus.received,
        index=True,
        comment="动作执行状态"
    )

    # 外部系统确认人ID（来自Agent，非本系统用户）
    confirmed_by_external: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="外部确认人ID")

    # 外部用户人工确认时间
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True,
                                                          comment="人工确认时间")

    # 动作实际执行完成时间
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="动作执行时间")

    # 执行成功后生成的业务资源类型（如 ticket）
    result_resource_type: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True,
                                                             comment="结果资源类型")

    # 执行成功后生成的业务资源ID（如工单ID）
    result_resource_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True, comment="结果资源ID")

    # 执行失败时的错误码
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="错误码")

    # 执行失败时的错误详情
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True, comment="错误信息")

    # 记录创建时间
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now,
                                                 comment="创建时间")

    # 记录更新时间，每次修改自动刷新
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
        comment="更新时间"
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

    # 主键ID，数据库唯一标识
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # 全局链路追踪ID，串联一次完整的Agent调用流程
    trace_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False,
                                          comment="全局链路ID，用于全流程问题排查")

    # Agent内部单次工具调用唯一ID，区分同一次链路中的不同工具调用
    tool_call_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False, comment="Agent工具调用唯一ID")

    # 外部会话ID，关联用户前端/外部系统会话
    external_session_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False,
                                                     comment="外部会话唯一标识")

    # 关联Agent侧pending_action业务ID，绑定业务动作
    pending_action_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False,
                                                   comment="关联的PendingAction ID")

    # 工具名称，标识当前调用的工具类型
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False, default="create_hr_ticket",
                                           comment="工具名称，默认创建HR工单")

    # 工具请求参数快照，完整保存Agent传入的所有参数
    request_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, comment="工具请求参数JSON快照")

    # 工具响应结果快照，完整保存后端返回的结果
    response_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, comment="工具响应结果JSON快照")

    # 工具调用执行状态
    status: Mapped[AgentToolCallStatus] = mapped_column(
        Enum(AgentToolCallStatus, name="agent_tool_call_status", native_enum=False),
        nullable=False,
        default=AgentToolCallStatus.received,
        index=True,
        comment="工具调用状态：已接收/成功/失败/重复/冲突"
    )

    # 错误码，调用失败时标识错误类型
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="错误码，调用失败时使用")

    # 错误信息，调用失败时记录详细原因
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True, comment="错误详情信息")

    # 接口耗时，单位：毫秒，用于性能监控
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="接口耗时（毫秒）")

    # 记录创建时间
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now,
                                                 comment="创建时间")

    # 记录更新时间，每次更新自动刷新
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
        comment="更新时间"
    )


class TicketPolicyReference(Base):
    """工单关联的 RAG 制度依据表。

    它回答的问题是：
    “Agent 创建这个 HR 工单时，依据了哪些制度文档和 chunk？”

    这不是 RAG 系统本身；它只是把 RAG 当时返回的关键 sources 做业务快照。
    这样即使之后知识库内容变化，仍然能解释当时为什么创建该工单。
    """

    __tablename__ = "ticket_policy_references"

    # 主键ID，数据库唯一标识
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # 关联的工单ID，与tickets表强关联，删除工单时级联删除本条依据
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tickets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="关联的工单ID"
    )

    # 外部会话ID，用于关联用户对话上下文
    external_session_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True,
                                                            comment="外部会话ID")

    # 关联Agent侧pending_action ID，绑定动作来源
    pending_action_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True,
                                                          comment="关联的PendingAction ID")

    # RAG检索时的用户原始问题
    rag_query: Mapped[str | None] = mapped_column(Text, nullable=True, comment="RAG检索的用户问题")

    # RAG生成的答案快照，存档不可修改
    rag_answer_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True, comment="RAG回答快照（存档）")

    # 知识库文档ID
    document_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True, comment="知识库文档ID")

    # 文档名称（如：员工手册、考勤制度）
    document_name: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="文档名称")

    # 知识库切片ID（RAG检索最小单元）
    chunk_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True, comment="文档切片ID")

    # 文档目录/路径层级（如：第一章->第二节）
    breadcrumb: Mapped[str | None] = mapped_column(String(500), nullable=True, comment="文档目录路径")

    # 文档页码（如PDF/Word页号）
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="文档页码")

    # 检索相关性得分（越高越匹配）
    retrieval_score: Mapped[float | None] = mapped_column(Float, nullable=True, comment="检索匹配度分数")

    # 文档切片原文快照，保证知识库更新后仍可查看历史依据
    content_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True, comment="制度条款原文快照")

    # 创建时间（记录生成本条依据的时间）
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now,
                                                 comment="创建时间")
