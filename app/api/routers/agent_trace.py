"""Agent observability routes.

第三阶段新增查询接口，用于查看 Agent 调用后端的执行链路。
这些接口主要给调试、运维、HR/admin 管理使用，不开放给 employee。
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, get_db
from app.models.user import User
from app.schemas.agent_trace import (
    AgentToolCallListResponse,
    PendingActionExecutionListResponse,
    PendingActionExecutionRead,
)
from app.services.agent_trace_service import AgentTraceService

router = APIRouter(tags=["agent-trace"])


@router.get("/agent-tool-calls", response_model=AgentToolCallListResponse)
def list_agent_tool_calls(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """查询 Agent 工具调用日志。

    用于回答：Agent 调用了哪个工具、请求是什么、响应是什么、是否失败。
    """
    items, total = AgentTraceService.list_agent_tool_calls(
        db,
        current_user=current_user,
        page=page,
        page_size=page_size,
    )
    return AgentToolCallListResponse(items=items, page=page, page_size=page_size, total=total)


@router.get("/pending-action-executions", response_model=PendingActionExecutionListResponse)
def list_pending_action_executions(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """查询 pending_action 执行记录。

    用于回答：用户确认的 pending_action 后端是否真正执行成功。
    """
    items, total = AgentTraceService.list_pending_action_executions(
        db,
        current_user=current_user,
        page=page,
        page_size=page_size,
    )
    return PendingActionExecutionListResponse(items=items, page=page, page_size=page_size, total=total)


@router.get("/pending-action-executions/{pending_action_id}", response_model=PendingActionExecutionRead)
def get_pending_action_execution(
    pending_action_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """查询某个 pending_action 的最近一次执行结果。"""
    return AgentTraceService.get_pending_action_execution(
        db,
        current_user=current_user,
        pending_action_id=pending_action_id,
    )
