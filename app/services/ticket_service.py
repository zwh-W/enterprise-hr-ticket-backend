import uuid
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictException, ForbiddenException, NotFoundException
from app.core.permissions import can_view_all_tickets, can_view_ticket
from app.models.ticket import Ticket, TicketStatus
from app.models.user import User
from app.repositories.audit_repo import AuditRepository
from app.repositories.ticket_repo import TicketRepository
from app.schemas.ticket import InternalTicketCreate, TicketCreate


def _ticket_audit_data(ticket: Ticket) -> dict[str, Any]:
    return {
        "id": str(ticket.id),
        "ticket_no": ticket.ticket_no,
        "ticket_type": ticket.ticket_type.value,
        "title": ticket.title,
        "status": ticket.status.value,
        "priority": ticket.priority.value,
        "creator_id": str(ticket.creator_id) if ticket.creator_id else None,
        "assignee_id": str(ticket.assignee_id) if ticket.assignee_id else None,
        "external_session_id": ticket.external_session_id,
        "created_by_external": ticket.created_by_external,
    }


class TicketService:
    @staticmethod
    def create_ticket_for_user(db: Session, *, payload: TicketCreate, creator: User) -> Ticket:
        try:
            ticket = TicketRepository.create(
                db,
                ticket_no=TicketRepository.generate_ticket_no(db),
                ticket_type=payload.ticket_type,
                title=payload.title,
                description=payload.description,
                priority=payload.priority,
                status=TicketStatus.open,
                creator_id=creator.id,
            )
            AuditRepository.create(
                db,
                user_id=creator.id,
                action="ticket.created",
                resource_type="ticket",
                resource_id=str(ticket.id),
                before_data=None,
                after_data=_ticket_audit_data(ticket),
            )
            db.commit()
            db.refresh(ticket)
            return ticket
        except IntegrityError as exc:
            db.rollback()
            raise ConflictException(message="Ticket number conflict. Please retry.") from exc
        except Exception:
            db.rollback()
            raise

    @staticmethod
    def create_ticket_from_internal(db: Session, *, payload: InternalTicketCreate) -> Ticket:
        try:
            ticket = TicketRepository.create(
                db,
                ticket_no=TicketRepository.generate_ticket_no(db),
                ticket_type=payload.ticket_type,
                title=payload.title,
                description=payload.description,
                priority=payload.priority,
                status=TicketStatus.open,
                creator_id=None,
                external_session_id=payload.external_session_id,
                created_by_external=payload.created_by_external,
            )
            AuditRepository.create(
                db,
                user_id=None,
                action="ticket.created_by_internal_api",
                resource_type="ticket",
                resource_id=str(ticket.id),
                before_data=None,
                after_data=_ticket_audit_data(ticket),
            )
            db.commit()
            db.refresh(ticket)
            return ticket
        except IntegrityError as exc:
            db.rollback()
            raise ConflictException(message="Ticket number conflict. Please retry.") from exc
        except Exception:
            db.rollback()
            raise

    @staticmethod
    def list_tickets(db: Session, *, current_user: User, page: int, page_size: int) -> tuple[list[Ticket], int]:
        offset = (page - 1) * page_size
        if can_view_all_tickets(current_user):
            return TicketRepository.list_all(db, offset=offset, limit=page_size)
        return TicketRepository.list_by_creator(db, creator_id=current_user.id, offset=offset, limit=page_size)

    @staticmethod
    def get_ticket(db: Session, *, ticket_id: uuid.UUID, current_user: User) -> Ticket:
        ticket = TicketRepository.get_by_id(db, ticket_id)
        if not ticket:
            raise NotFoundException(message="Ticket not found.")
        if not can_view_ticket(current_user, ticket.creator_id):
            raise ForbiddenException(message="You do not have permission to access this ticket.")
        return ticket
