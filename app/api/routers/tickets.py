import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, get_db
from app.models.user import User
from app.schemas.ticket import TicketCreate, TicketListResponse, TicketPolicyReferenceListResponse, TicketRead
from app.services.ticket_service import TicketService

router = APIRouter(prefix="/tickets", tags=["tickets"])


@router.post("", response_model=TicketRead, status_code=status.HTTP_201_CREATED)
def create_ticket(
    payload: TicketCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """登录用户创建自己的 HR 工单。"""
    return TicketService.create_ticket_for_user(db, payload=payload, creator=current_user)


@router.get("", response_model=TicketListResponse)
def list_tickets(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """按权限查询工单列表。

    employee 只能看到自己的工单；hr/admin 可以看到全部工单。
    """
    items, total = TicketService.list_tickets(db, current_user=current_user, page=page, page_size=page_size)
    return TicketListResponse(items=items, page=page, page_size=page_size, total=total)


@router.get("/{ticket_id}", response_model=TicketRead)
def get_ticket(
    ticket_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """查询工单详情，并在 service 层做资源级权限判断。"""
    return TicketService.get_ticket(db, ticket_id=ticket_id, current_user=current_user)


@router.get("/{ticket_id}/policy-references", response_model=TicketPolicyReferenceListResponse)
def list_ticket_policy_references(
    ticket_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """查询某张工单对应的 RAG 制度依据。

    这个接口用于验证第三阶段的 evidence 落库结果。
    权限沿用工单详情权限。
    """
    items = TicketService.list_policy_references(db, ticket_id=ticket_id, current_user=current_user)
    return TicketPolicyReferenceListResponse(items=items)
