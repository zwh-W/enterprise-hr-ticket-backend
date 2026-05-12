from app.core.exceptions import ForbiddenException
from app.models.user import User, UserRole


def ensure_role(user: User, allowed_roles: set[UserRole]) -> None:
    if user.role not in allowed_roles:
        allowed = ", ".join(sorted(role.value for role in allowed_roles))
        raise ForbiddenException(message=f"Required role: {allowed}.")


def can_view_all_tickets(user: User) -> bool:
    return user.role in {UserRole.admin, UserRole.hr}


def can_view_ticket(user: User, creator_id: object | None) -> bool:
    if can_view_all_tickets(user):
        return True
    return creator_id is not None and user.id == creator_id


def can_view_audit_logs(user: User) -> bool:
    return user.role in {UserRole.admin, UserRole.hr}
