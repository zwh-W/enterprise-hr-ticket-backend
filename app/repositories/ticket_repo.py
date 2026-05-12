import uuid
from datetime import timezone, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.ticket import Ticket


class TicketRepository:
    @staticmethod
    def generate_ticket_no(db: Session) -> str:
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        prefix = f"HR-{today}-"
        stmt = select(func.count(Ticket.id)).where(Ticket.ticket_no.like(f"{prefix}%"))
        count = db.scalar(stmt) or 0
        return f"{prefix}{count + 1:04d}"

    @staticmethod
    def create(db: Session, **data: object) -> Ticket:
        ticket = Ticket(**data)
        db.add(ticket)
        db.flush()
        return ticket

    @staticmethod
    def get_by_id(db: Session, ticket_id: uuid.UUID) -> Ticket | None:
        return db.get(Ticket, ticket_id)

    @staticmethod
    def list_all(db: Session, *, offset: int, limit: int) -> tuple[list[Ticket], int]:
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
