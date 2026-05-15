"""Schemas for ticket status transition APIs."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.ticket import TicketStatus
from app.models.user import UserRole


class TicketStatusUpdate(BaseModel):
    """PATCH /tickets/{ticket_id}/status 请求体。"""

    status: TicketStatus
    reason: str | None = Field(default=None, max_length=1000)


class TicketAssignRequest(BaseModel):
    """PATCH /tickets/{ticket_id}/assign 请求体。"""

    assignee_id: uuid.UUID
    reason: str | None = Field(default=None, max_length=1000)


class TicketCancelRequest(BaseModel):
    """POST /tickets/{ticket_id}/cancel 请求体。"""

    reason: str | None = Field(default=None, max_length=1000)


class TicketStatusTransitionRead(BaseModel):
    """状态流转记录响应体。"""

    id: uuid.UUID
    ticket_id: uuid.UUID
    from_status: TicketStatus
    to_status: TicketStatus
    operator_id: uuid.UUID | None
    operator_role: UserRole
    reason: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TicketStatusTransitionListResponse(BaseModel):
    """某张工单的状态流转历史列表。"""

    items: list[TicketStatusTransitionRead]
