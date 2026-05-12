from sqlalchemy.orm import Session

from app.core.exceptions import ForbiddenException
from app.models.user import User, UserRole
from app.repositories.audit_repo import AuditRepository


class AuditService:
    @staticmethod
    def list_audit_logs(db: Session, *, current_user: User, page: int, page_size: int):
        if current_user.role == UserRole.employee:
            raise ForbiddenException(message="Employees are not allowed to view audit logs.")

        offset = (page - 1) * page_size
        if current_user.role == UserRole.hr:
            return AuditRepository.list_by_resource_type(db, resource_type="ticket", offset=offset, limit=page_size)

        return AuditRepository.list_all(db, offset=offset, limit=page_size)
