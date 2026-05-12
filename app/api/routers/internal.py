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
    return TicketService.create_ticket_from_internal(db, payload=payload)
