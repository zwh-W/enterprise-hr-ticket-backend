"""Central model import module.

导入此模块会加载全部 ORM 模型，使 SQLAlchemy Base.metadata 包含所有表。
Alembic 自动生成迁移时会 import app.models。
"""

from app.models.agent_trace import (
    AgentToolCall,
    AgentToolCallStatus,
    PendingActionExecution,
    PendingActionExecutionStatus,
    TicketPolicyReference,
)
from app.models.audit_log import AuditLog
from app.models.idempotency import IdempotencyKey, IdempotencyStatus
from app.models.ticket import Ticket, TicketPriority, TicketStatus, TicketType
from app.models.ticket_transition import TicketStatusTransition
from app.models.user import User, UserRole

__all__ = [
    "User",
    "UserRole",
    "Ticket",
    "TicketType",
    "TicketStatus",
    "TicketPriority",
    "TicketStatusTransition",
    "AuditLog",
    "IdempotencyKey",
    "IdempotencyStatus",
    "PendingActionExecution",
    "PendingActionExecutionStatus",
    "AgentToolCall",
    "AgentToolCallStatus",
    "TicketPolicyReference",
]
