import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, get_db
from app.models.user import User
from app.schemas.ticket import TicketCreate, TicketListResponse, TicketPolicyReferenceListResponse, TicketRead
from app.schemas.ticket_transition import (
    TicketAssignRequest,
    TicketCancelRequest,
    TicketStatusTransitionListResponse,
    TicketStatusUpdate,
)
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
    """按权限查询工单列表。"""
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


@router.patch("/{ticket_id}/status", response_model=TicketRead)
def update_ticket_status(
    ticket_id: uuid.UUID,
    payload: TicketStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """按轻量状态机更新工单状态。

    第四阶段重点：不能任意改 status，必须经过 service 层状态机和权限校验。
    """
    return TicketService.update_status(db, ticket_id=ticket_id, payload=payload, current_user=current_user)


@router.patch("/{ticket_id}/assign", response_model=TicketRead)
def assign_ticket(
    ticket_id: uuid.UUID,
    payload: TicketAssignRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """HR / admin 分配工单处理人。"""
    return TicketService.assign_ticket(db, ticket_id=ticket_id, payload=payload, current_user=current_user)


@router.post("/{ticket_id}/cancel", response_model=TicketRead)
def cancel_ticket(
    ticket_id: uuid.UUID,
    payload: TicketCancelRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """取消 open 状态工单。"""
    return TicketService.cancel_ticket(db, ticket_id=ticket_id, payload=payload, current_user=current_user)


@router.get("/{ticket_id}/transitions", response_model=TicketStatusTransitionListResponse)
def list_ticket_transitions(
    ticket_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """查询某张工单的状态流转历史。"""
    items = TicketService.list_transitions(db, ticket_id=ticket_id, current_user=current_user)
    return TicketStatusTransitionListResponse(items=items)


@router.get("/{ticket_id}/policy-references", response_model=TicketPolicyReferenceListResponse)
def list_ticket_policy_references(
    ticket_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """查询某张工单对应的 RAG 制度依据。"""
    items = TicketService.list_policy_references(db, ticket_id=ticket_id, current_user=current_user)
    return TicketPolicyReferenceListResponse(items=items)
