"""Ticket request and response schemas.

Schema 面向 HTTP 输入输出；Model 面向数据库表结构。
不要把 ORM Model 原封不动暴露给前端或外部服务。
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.ticket import TicketPriority, TicketStatus, TicketType


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

    第二阶段新增 pending_action_id 和 idempotency_key：
    - pending_action_id：Agent 侧 pending_action 的业务 ID。
    - idempotency_key：用于防止重复创建真实 ticket。
    """

    external_session_id: str = Field(min_length=1, max_length=128)  # Agent 会话 ID
    pending_action_id: str = Field(min_length=1, max_length=128)  # Agent 生成的待确认动作 ID
    idempotency_key: str = Field(min_length=8, max_length=255)  # 防止重复创建真实工单的幂等键
    ticket_type: TicketType
    title: str = Field(min_length=2, max_length=255)
    description: str = Field(min_length=1)
    created_by_external: str = Field(min_length=1, max_length=128)
    priority: TicketPriority = TicketPriority.normal


class InternalTicketResponse(BaseModel):
    """Internal API 创建工单响应体。

    response_model 支持从 ORM 对象读取字段，所以开启 from_attributes。
    """

    id: uuid.UUID
    ticket_no: str
    ticket_type: TicketType
    title: str
    status: TicketStatus
    pending_action_id: str | None = None
    idempotency_key: str | None = None

    model_config = ConfigDict(from_attributes=True)
