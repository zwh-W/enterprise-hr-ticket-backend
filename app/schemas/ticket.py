import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.ticket import TicketPriority, TicketStatus, TicketType


class TicketCreate(BaseModel):
    ticket_type: TicketType
    title: str = Field(min_length=2, max_length=255)
    description: str = Field(min_length=1)
    priority: TicketPriority = TicketPriority.normal


class TicketRead(BaseModel):
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
    created_by_external: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TicketListResponse(BaseModel):
    items: list[TicketRead]
    page: int
    page_size: int
    total: int


class InternalTicketCreate(BaseModel):
    external_session_id: str = Field(min_length=1, max_length=128)
    ticket_type: TicketType
    title: str = Field(min_length=2, max_length=255)
    description: str = Field(min_length=1)
    created_by_external: str = Field(min_length=1, max_length=128)
    priority: TicketPriority = TicketPriority.normal


class InternalTicketResponse(BaseModel):
    ticket_no: str
    ticket_type: TicketType
    title: str
    status: TicketStatus
