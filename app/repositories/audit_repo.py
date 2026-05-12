import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


class AuditRepository:
    @staticmethod
    def create(
            db: Session,
            *,
            user_id: uuid.UUID | None,
            action: str,
            resource_type: str,
            resource_id: str,
            before_data: dict[str, Any] | None = None,
            after_data: dict[str, Any] | None = None,
    ) -> AuditLog:
        audit_log = AuditLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            before_data=before_data,
            after_data=after_data,
        )
        db.add(audit_log)
        db.flush()
        return audit_log

    @staticmethod
    def list_all(db: Session, *, offset: int, limit: int) -> tuple[list[AuditLog], int]:
        total = db.scalar(select(func.count(AuditLog.id))) or 0
        stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).offset(offset).limit(limit)
        return list(db.scalars(stmt).all()), total

    @staticmethod
    def list_by_resource_type(
            db: Session,
            *,
            resource_type: str,
            offset: int,
            limit: int,
    ) -> tuple[list[AuditLog], int]:
        total_stmt = select(func.count(AuditLog.id)).where(AuditLog.resource_type == resource_type)
        total = db.scalar(total_stmt) or 0
        stmt = (
            select(AuditLog)
            .where(AuditLog.resource_type == resource_type)
            .order_by(AuditLog.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(db.scalars(stmt).all()), total
