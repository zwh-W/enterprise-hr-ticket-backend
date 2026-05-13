"""Internal service-to-service routes.

Internal API 专门给 Agent 服务调用，不使用用户 JWT。
调用方需要携带 X-Internal-API-Key。
第二阶段开始，这个接口支持 idempotency_key，防止 Agent 重复确认导致重复建单。
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, verify_internal_api_key
from app.schemas.ticket import InternalTicketCreate, InternalTicketResponse
from app.services.ticket_service import TicketService

router = APIRouter(prefix="/internal", tags=["internal"])


@router.post(
    "/tickets",
    response_model=InternalTicketResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_internal_api_key)],
)
def create_ticket_from_internal(payload: InternalTicketCreate, db: Session = Depends(get_db)):
    """Agent 确认 pending_action 后创建真实 HR 工单。

    幂等规则由 TicketService.create_ticket_from_internal 负责。
    Router 不直接写数据库，也不做幂等业务判断。
    """
    return TicketService.create_ticket_from_internal(db, payload=payload)
