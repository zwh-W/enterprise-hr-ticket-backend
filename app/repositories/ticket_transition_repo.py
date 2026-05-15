"""Repository for ticket status transitions.

Repository 层只负责数据库读写，不判断“某个角色能不能做某个状态流转”。
状态机规则和权限规则属于 service 层职责。
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ticket import TicketStatus
from app.models.ticket_transition import TicketStatusTransition
from app.models.user import UserRole


class TicketStatusTransitionRepository:
    """工单状态流转记录的数据访问对象。"""

    @staticmethod
    def create(
            db: Session,  # 数据库会话对象，用于执行数据库增删改查操作
            *,  # Python 语法：强制后面的参数在调用时必须指定参数名（关键字参数）
            ticket_id: uuid.UUID,  # 发生状态流转的工单的唯一标识 ID
            from_status: TicketStatus,  # 流转前的状态（起点）
            to_status: TicketStatus,  # 流转后的状态（终点）
            operator_id: uuid.UUID | None,  # 执行操作的用户 ID（允许为 None，通常用于系统自动触发的流转）
            operator_role: UserRole,  # 执行操作时的用户角色（当时是管理员还是 HR，防止以后角色变更导致历史记录说不清）
            reason: str | None,  # 状态变更的原因或备注留言（可选）
    ) -> TicketStatusTransition:  # 类型提示：函数将返回一个 TicketStatusTransition（工单状态流转记录）对象
        """创建一条状态流转记录。"""

        # 1. 实例化：将传入的数据打包，创建一个新的流转记录对象
        transition = TicketStatusTransition(
            ticket_id=ticket_id,
            from_status=from_status,
            to_status=to_status,
            operator_id=operator_id,
            operator_role=operator_role,
            reason=reason,
        )

        # 2. 暂存：将这个新创建的对象添加到当前的数据库会话中
        db.add(transition)

        # 3. 刷入：将数据推送到数据库执行（此时数据已在数据库中产生，但事务尚未最终 commit 提交）。
        # 这一步的作用通常是为了让数据库自动生成自增 ID 或默认时间戳，以便后续代码直接使用。
        db.flush()

        # 4. 返回：将包含完整信息的记录对象返回给调用方
        return transition

    @staticmethod
    def list_by_ticket_id(db: Session, *, ticket_id: uuid.UUID) -> list[TicketStatusTransition]:
        """按时间顺序查询某张工单的状态流转历史。"""
        stmt = (
            select(TicketStatusTransition)
            .where(TicketStatusTransition.ticket_id == ticket_id)
            .order_by(TicketStatusTransition.created_at.asc())
        )
        return list(db.scalars(stmt).all())
