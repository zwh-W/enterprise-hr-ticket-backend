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

    external_session_id: str = Field(min_length=1, max_length=128)
    pending_action_id: str = Field(min_length=1, max_length=128)
    idempotency_key: str = Field(min_length=8, max_length=255)

    # trace_id / tool_call_id 如果 Agent 暂时不传，后端会自动生成，保证接口兼容第二阶段。
    trace_id: str | None = Field(default=None, max_length=128)
    tool_call_id: str | None = Field(default=None, max_length=128)
    tool_name: str = Field(default="create_hr_ticket", max_length=100)

    ticket_type: TicketType
    title: str = Field(min_length=2, max_length=255)
    description: str = Field(min_length=1)
    created_by_external: str = Field(min_length=1, max_length=128)
    priority: TicketPriority = TicketPriority.normal

    confirmed_by_external: str | None = Field(default=None, max_length=128)
    confirmed_at: datetime | None = None

    rag_answer_snapshot: str | None = None
    rag_references: list[RagReferenceCreate] = Field(default_factory=list)

    # Agent 原始 trace 摘要，存入 agent_tool_calls.request_payload，方便排查。
    agent_trace: dict[str, Any] | None = None


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
