import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, get_db
from app.models.user import User
from app.schemas.ticket import TicketCreate, TicketListResponse, TicketRead
from app.services.ticket_service import TicketService

router = APIRouter(prefix="/tickets", tags=["tickets"])




@router.post("", response_model=TicketRead, status_code=status.HTTP_201_CREATED)
def create_ticket(
        payload: TicketCreate,  # 前端传过来的数据
        db: Session = Depends(get_db),  # 数据库连接
        current_user: User = Depends(get_current_active_user),  # 当前登录用户
):
    return TicketService.create_ticket_for_user(db, payload=payload, creator=current_user)


@router.get("", response_model=TicketListResponse)
def list_tickets(
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, ge=1, le=100),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_active_user),
):
    items, total = TicketService.list_tickets(db, current_user=current_user, page=page, page_size=page_size)
    return TicketListResponse(items=items, page=page, page_size=page_size, total=total)


@router.get("/{ticket_id}", response_model=TicketRead)
def get_ticket(
        ticket_id: uuid.UUID,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_active_user),
):
    return TicketService.get_ticket(db, ticket_id=ticket_id, current_user=current_user)
