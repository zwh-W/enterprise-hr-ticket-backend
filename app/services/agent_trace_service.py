"""Read services for Agent trace and pending action execution records.

写入逻辑主要发生在 TicketService.create_ticket_from_internal，因为它需要和创建 ticket、幂等记录、审计日志放在同一个事务里。
这里主要提供查询服务，并做权限校验。
"""

from sqlalchemy.orm import Session

from app.core.exceptions import ForbiddenException, NotFoundException
from app.models.user import User, UserRole
from app.repositories.agent_trace_repo import AgentToolCallRepository, PendingActionExecutionRepository


class AgentTraceService:
    """Agent trace 查询服务。"""

    @staticmethod
    def _ensure_hr_or_admin(current_user: User) -> None:
        """第三阶段只允许 hr/admin 查看 Agent 执行链路。"""
        if current_user.role not in {UserRole.hr, UserRole.admin}:
            raise ForbiddenException(message="Employees are not allowed to view Agent trace records.")

    @staticmethod
    def list_agent_tool_calls(db: Session, *, current_user: User, page: int, page_size: int):
        """分页查询 Agent 工具调用日志。"""
        AgentTraceService._ensure_hr_or_admin(current_user)
        offset = (page - 1) * page_size
        return AgentToolCallRepository.list_all(db, offset=offset, limit=page_size)

    @staticmethod
    def list_pending_action_executions(db: Session, *, current_user: User, page: int, page_size: int):
        """分页查询 pending_action 执行记录。"""
        AgentTraceService._ensure_hr_or_admin(current_user)
        offset = (page - 1) * page_size
        return PendingActionExecutionRepository.list_all(db, offset=offset, limit=page_size)

    @staticmethod
    def get_pending_action_execution(db: Session, *, current_user: User, pending_action_id: str):
        """查询某个 pending_action 的最近一次执行记录。"""
        AgentTraceService._ensure_hr_or_admin(current_user)
        item = PendingActionExecutionRepository.get_by_pending_action_id(db, pending_action_id)
        if not item:
            raise NotFoundException(message="Pending action execution not found.")
        return item
