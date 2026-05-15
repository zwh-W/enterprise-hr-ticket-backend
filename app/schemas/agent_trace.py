"""Pydantic schemas for Agent trace and RAG evidence.

这些 schema 面向 HTTP 输入输出，不直接等同于 ORM model。
第三阶段重点是把 Agent / RAG 的执行上下文保存成可查询、可审计的数据。
"""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.agent_trace import AgentToolCallStatus, PendingActionExecutionStatus


class RagReferenceCreate(BaseModel):
    """Internal API 中传入的一条 RAG source 快照。

    字段命名尽量兼容常见 RAG 返回：document_id、chunk_id、breadcrumb、score/content。
    后续接入你自己的 RAG 项目时，只需要做字段映射。
    """

    rag_query: str | None = Field(default=None, max_length=2000)
    document_id: str | None = Field(default=None, max_length=128)
    document_name: str | None = Field(default=None, max_length=255)
    chunk_id: str | None = Field(default=None, max_length=128)
    breadcrumb: str | None = Field(default=None, max_length=500)
    page_number: int | None = Field(default=None, ge=1)
    retrieval_score: float | None = None
    content_snapshot: str | None = None


class TicketPolicyReferenceRead(BaseModel):
    """返回给前端 / 调试工具的工单 RAG 依据。"""

    id: uuid.UUID
    ticket_id: uuid.UUID
    external_session_id: str | None
    pending_action_id: str | None
    rag_query: str | None
    rag_answer_snapshot: str | None
    document_id: str | None
    document_name: str | None
    chunk_id: str | None
    breadcrumb: str | None
    page_number: int | None
    retrieval_score: float | None
    content_snapshot: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AgentToolCallRead(BaseModel):
    """Agent 工具调用日志响应体。"""

    id: uuid.UUID
    trace_id: str
    tool_call_id: str
    external_session_id: str
    pending_action_id: str
    tool_name: str
    request_payload: dict[str, Any] | None
    response_payload: dict[str, Any] | None
    status: AgentToolCallStatus
    error_code: str | None
    error_message: str | None
    latency_ms: int | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AgentToolCallListResponse(BaseModel):
    """Agent 工具调用日志分页响应。"""

    items: list[AgentToolCallRead]
    page: int
    page_size: int
    total: int


class PendingActionExecutionRead(BaseModel):
    """pending_action 执行记录响应体。"""

    id: uuid.UUID
    external_session_id: str
    pending_action_id: str
    idempotency_key: str
    action_type: str
    status: PendingActionExecutionStatus
    confirmed_by_external: str | None
    confirmed_at: datetime | None
    executed_at: datetime | None
    result_resource_type: str | None
    result_resource_id: str | None
    error_code: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PendingActionExecutionListResponse(BaseModel):
    """pending_action 执行记录分页响应。"""

    items: list[PendingActionExecutionRead]
    page: int
    page_size: int
    total: int
