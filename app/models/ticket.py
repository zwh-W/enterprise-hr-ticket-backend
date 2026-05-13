"""Ticket ORM model.

Ticket 是 HR 工单系统的核心业务实体。
第二阶段新增了 pending_action_id 和 idempotency_key，用于把 Agent pending_action
和真实落库工单关联起来，并支持 Internal API 幂等创建。
"""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.security import utc_now
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class TicketType(str, enum.Enum):
    """工单类型。"""

    leave_request = "leave_request"
    reimbursement = "reimbursement"
    salary_inquiry = "salary_inquiry"
    social_security = "social_security"
    onboarding = "onboarding"
    offboarding = "offboarding"
    general_hr = "general_hr"
    equipment_request = "equipment_request"


class TicketStatus(str, enum.Enum):
    """工单状态。第一阶段只创建 open；后续阶段会扩展状态机。"""

    open = "open"
    processing = "processing"
    resolved = "resolved"
    closed = "closed"
    cancelled = "cancelled"


class TicketPriority(str, enum.Enum):
    """工单优先级。"""

    low = "low"
    normal = "normal"
    high = "high"
    urgent = "urgent"


class Ticket(Base):
    """HR 工单表。"""

    __tablename__ = "tickets"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # 对外展示的工单编号，格式示例：HR-20260513-0001。
    ticket_no: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)

    ticket_type: Mapped[TicketType] = mapped_column(
        Enum(TicketType, name="ticket_type", native_enum=False),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[TicketStatus] = mapped_column(
        Enum(TicketStatus, name="ticket_status", native_enum=False),
        nullable=False,
        default=TicketStatus.open,
        index=True,
    )
    priority: Mapped[TicketPriority] = mapped_column(
        Enum(TicketPriority, name="ticket_priority", native_enum=False),
        nullable=False,
        default=TicketPriority.normal,
        index=True,
    )

    # 普通用户创建的工单会有 creator_id；Internal API 创建时可为空。
    creator_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Agent 会话 ID，用于从后端反查某个会话产生了哪些工单。
    external_session_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)

    # Agent pending_action ID，用于把“用户确认的动作”和真实 ticket 对齐。
    pending_action_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)

    # Internal API 幂等键。nullable + unique 在 PostgreSQL / SQLite 中允许多条 NULL。
    # Internal API 创建的 ticket 会写入该字段；用户手动创建的 ticket 为空。
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True, index=True)

    # 外部创建来源，例如 agent:test-session-ticket-001。
    created_by_external: Mapped[str | None] = mapped_column(String(128), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    creator: Mapped["User | None"] = relationship(
        "User",
        foreign_keys=[creator_id],
        back_populates="created_tickets",
    )
    assignee: Mapped["User | None"] = relationship(
        "User",
        foreign_keys=[assignee_id],
        back_populates="assigned_tickets",
    )
