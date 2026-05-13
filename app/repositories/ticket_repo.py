"""Ticket repository.

Repository 层只处理数据库查询与写入，不判断业务权限，也不决定状态流转规则。
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.ticket import Ticket


class TicketRepository:
    """工单数据访问对象。"""

    @staticmethod
    def generate_ticket_no(db: Session) -> str:
        """生成当天递增工单号。

        第一阶段/第二阶段采用简单 count 方式，便于理解。
        后续如果考虑高并发，需要改成数据库序列或单独编号表。
        """
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        prefix = f"HR-{today}-"
        stmt = select(func.count(Ticket.id)).where(Ticket.ticket_no.like(f"{prefix}%"))
        count = db.scalar(stmt) or 0
        return f"{prefix}{count + 1:04d}"

    @staticmethod
    def create(db: Session, **data: object) -> Ticket:
        """创建工单并 flush，使 ticket.id 立即可用于审计日志。"""
        ticket = Ticket(**data)
        db.add(ticket)
        db.flush()
        return ticket

    @staticmethod
    def get_by_id(db: Session, ticket_id: uuid.UUID) -> Ticket | None:
        """根据主键查询工单。"""
        return db.get(Ticket, ticket_id)

    @staticmethod
    def get_by_idempotency_key(db: Session, idempotency_key: str) -> Ticket | None:
        """根据幂等键查询已创建的工单。"""
        stmt = select(Ticket).where(Ticket.idempotency_key == idempotency_key)
        return db.scalar(stmt)

    @staticmethod
    def list_all(db: Session, *, offset: int, limit: int) -> tuple[list[Ticket], int]:
        """查询全部工单，供 hr/admin 使用。"""
        total = db.scalar(select(func.count(Ticket.id))) or 0
        stmt = select(Ticket).order_by(Ticket.created_at.desc()).offset(offset).limit(limit)
        return list(db.scalars(stmt).all()), total

    @staticmethod
    def list_by_creator(
        db: Session,
        *,
        creator_id: uuid.UUID,
        offset: int,
        limit: int,
    ) -> tuple[list[Ticket], int]:
        """查询某个员工自己创建的工单。"""
        total_stmt = select(func.count(Ticket.id)).where(Ticket.creator_id == creator_id)
        total = db.scalar(total_stmt) or 0
        stmt = (
            select(Ticket)
            .where(Ticket.creator_id == creator_id)
            .order_by(Ticket.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(db.scalars(stmt).all()), total
