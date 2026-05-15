"""Ticket status transition ORM model.

第四阶段新增 ticket_status_transitions 表，用来记录每一次工单状态变化。

为什么不只看 tickets.status？
- tickets.status 只能告诉你“现在是什么状态”。
- ticket_status_transitions 能告诉你“状态是怎么一步步变成现在这样的”。

这张表回答的问题是：
谁在什么时候，把哪个工单，从什么状态改到了什么状态，原因是什么。
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.security import utc_now
from app.db.base import Base
from app.models.ticket import TicketStatus
from app.models.user import UserRole

if TYPE_CHECKING:
    from app.models.ticket import Ticket
    from app.models.user import User


class TicketStatusTransition(Base):
    """工单状态流转记录表：用于追踪每一个工单状态变更的历史。"""

    # 数据库中实际的表名
    __tablename__ = "ticket_status_transitions"

    # 主键 ID：每一条流转记录的唯一标识，使用 UUID 保证全局唯一
    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )

    # 关联的工单 ID：指明这条记录属于哪个工单
    # ForeignKey: 建立外键关联到 tickets 表
    # ondelete="CASCADE": 如果对应的工单被删除了，这条流转记录也随之自动删除
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tickets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,  # 添加索引以提高查询该工单历史记录的速度
    )

    # 起始状态：流转发生前的状态
    from_status: Mapped[TicketStatus] = mapped_column(
        Enum(TicketStatus, name="ticket_transition_from_status", native_enum=False),
        nullable=False,
    )

    # 目标状态：流转发生后的状态
    to_status: Mapped[TicketStatus] = mapped_column(
        Enum(TicketStatus, name="ticket_transition_to_status", native_enum=False),
        nullable=False,
    )

    # 操作人 ID：谁执行了这次状态变更？
    # nullable=True: 允许为空，因为有些流转可能是系统脚本自动完成的
    # ondelete="SET NULL": 如果操作员账号被删了，保留此记录，但将操作人字段设为空
    operator_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # 操作人角色：记录操作发生时该用户的身份（Admin/HR/Employee）
    operator_role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="ticket_transition_operator_role", native_enum=False),
        nullable=False,
    )

    # 变更原因：记录为什么要改状态（比如 HR 留言：“资料不全，驳回”）
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 创建时间：这条流转记录产生的精确时间，默认使用当前 UTC 时间
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now
    )

    # --- 关系映射（SQLAlchemy Relationship） ---
    # 允许你在代码中通过 transition.ticket 直接访问到对应的工单对象
    ticket: Mapped["Ticket"] = relationship("Ticket", back_populates="transitions")

    # 允许通过 transition.operator 直接访问到对应的用户信息
    operator: Mapped["User | None"] = relationship("User")