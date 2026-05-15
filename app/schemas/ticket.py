"""Ticket request and response schemas.

Schema 面向 HTTP 输入输出；Model 面向数据库表结构。
第三阶段扩展 InternalTicketCreate，使 Agent 可以把 trace、pending_action 确认信息、RAG sources
一起传给后端，后端再统一落库。
"""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.ticket import TicketPriority, TicketStatus, TicketType
from app.schemas.agent_trace import RagReferenceCreate, TicketPolicyReferenceRead


class TicketCreate(BaseModel):
    """登录用户创建工单的请求体。"""

    ticket_type: TicketType
    title: str = Field(min_length=2, max_length=255)
    description: str = Field(min_length=1)
    priority: TicketPriority = TicketPriority.normal


class TicketRead(BaseModel):
    """普通工单响应体。"""

    id: uuid.UUID
    ticket_no: str
    ticket_type: TicketType
    title: str
    description: str
    status: TicketStatus
    priority: TicketPriority
    creator_id: uuid.UUID | None
    assignee_id: uuid.UUID | None
    external_session_id: str | None = None
    pending_action_id: str | None = None
    idempotency_key: str | None = None
    created_by_external: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TicketListResponse(BaseModel):
    """工单分页列表响应体。"""

    items: list[TicketRead]
    page: int
    page_size: int
    total: int


class InternalTicketCreate(BaseModel):
    """Internal API 创建工单请求体。

    第二阶段字段：
    - pending_action_id：Agent 侧 pending_action 的业务 ID。
    - idempotency_key：防止重复创建真实 ticket。

    第三阶段字段：
    - trace_id / tool_call_id / tool_name：把 Agent 工具调用链路和真实 ticket 对齐。
    - confirmed_by_external / confirmed_at：保存 Human-in-the-loop 确认信息。
    - rag_answer_snapshot / rag_references：保存 RAG 制度依据快照。
    - agent_trace：保存 Agent 侧 trace 摘要；它不参与核心业务建模，只用于排查。
    """

    # 外部会话唯一标识，关联前端/外部系统会话，必填
    external_session_id: str = Field(
        min_length=1, max_length=128,
        description="外部会话ID，关联前端/外部系统会话上下文"
    )

    # Agent侧待处理动作的业务ID，第二阶段必填关键字段
    pending_action_id: str = Field(
        min_length=1, max_length=128,
        description="Agent侧pending_action业务唯一ID"
    )

    # 幂等键，用于防止重复创建工单，必填
    idempotency_key: str = Field(
        min_length=8, max_length=255,
        description="幂等键，保证请求幂等性，避免重复创建真实工单"
    )

    # 链路追踪ID，不传则后端自动生成，保证接口向下兼容
    trace_id: str | None = Field(
        default=None, max_length=128,
        description="链路追踪ID，未传入时后端自动生成"
    )

    # 工具调用ID，不传则后端自动生成，保证接口向下兼容
    tool_call_id: str | None = Field(
        default=None, max_length=128,
        description="Agent工具调用ID，未传入时后端自动生成"
    )

    # 调用的工具名称，固定默认值
    tool_name: str = Field(
        default="create_hr_ticket", max_length=100,
        description="调用的工具名称，默认创建HR工单"
    )

    # 工单类型，业务枚举必填
    ticket_type: TicketType = Field(
        description="工单类型（业务枚举）"
    )

    # 工单标题，必填
    title: str = Field(
        min_length=2, max_length=255,
        description="工单标题"
    )

    # 工单描述/详情，必填
    description: str = Field(
        min_length=1,
        description="工单详细描述内容"
    )

    # 外部系统创建人标识，必填
    created_by_external: str = Field(
        min_length=1, max_length=128,
        description="外部系统创建人唯一标识"
    )

    # 工单优先级，默认普通优先级
    priority: TicketPriority = Field(
        default=TicketPriority.normal,
        description="工单优先级，默认为普通"
    )

    # 人工确认人标识（Human-in-the-loop），可选
    confirmed_by_external: str | None = Field(
        default=None, max_length=128,
        description="人工复核确认人标识（人在回路）"
    )

    # 人工确认时间，可选
    confirmed_at: datetime | None = Field(
        default=None,
        description="人工复核确认时间"
    )

    # RAG智能回答快照，用于存档溯源
    rag_answer_snapshot: str | None = Field(
        default=None,
        description="RAG制度依据回答快照（存档用）"
    )

    # RAG参考文档/制度列表，默认空列表
    rag_references: list[RagReferenceCreate] = Field(
        default_factory=list,
        description="RAG参考依据列表"
    )

    # Agent原始追踪数据，仅用于问题排查，不参与业务逻辑
    agent_trace: dict[str, Any] | None = Field(
        default=None,
        description="Agent调用链路摘要，仅用于问题排查"
    )


class InternalTicketResponse(BaseModel):
    """Internal API 创建工单响应体。"""

    id: uuid.UUID
    ticket_no: str
    ticket_type: TicketType
    title: str
    status: TicketStatus
    pending_action_id: str | None = None
    idempotency_key: str | None = None

    model_config = ConfigDict(from_attributes=True)


class TicketPolicyReferenceListResponse(BaseModel):
    """某张工单的 RAG 依据列表响应。"""

    items: list[TicketPolicyReferenceRead]
