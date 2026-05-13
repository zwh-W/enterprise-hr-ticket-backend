"""Idempotency model.

第二阶段核心表：idempotency_keys。
幂等键表
它用于解决 Agent / 外部服务重复调用 Internal API 时重复创建工单的问题。

典型场景：
- Agent 调用后端创建工单成功，但网络超时，Agent 没拿到响应。
- 用户重复点击确认，Agent 重复发起创建请求。
- Agent 任务重试机制重复发送同一个 pending_action。

后端通过 idempotency_key 保证：同一个业务请求最多创建一个真实 ticket。
"""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, JSON, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.security import utc_now
from app.db.base import Base


class IdempotencyStatus(str, enum.Enum):
    """幂等请求处理状态。"""

    processing = "processing"  # 请求已登记，正在处理。
    succeeded = "succeeded"  # 请求处理成功，可直接复用资源和响应。
    failed = "failed"  # 请求处理失败，预留给后续失败重试策略。


class IdempotencyKey(Base):
    """幂等键表。

    一条记录代表一个外部请求的幂等身份。
    """

    __tablename__ = "idempotency_keys"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # 外部调用方传入的唯一幂等键。必须唯一。
    # 建议格式：agent:<pending_action_id>:create_ticket
    key: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)

    # 对请求体核心字段做 sha256 哈希。
    # 如果同一个 key 携带不同请求体，说明调用方重复使用 key，应返回 409。
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    status: Mapped[IdempotencyStatus] = mapped_column(
        Enum(IdempotencyStatus, name="idempotency_status", native_enum=False),
        nullable=False,
        default=IdempotencyStatus.processing,
        index=True,
    )

    # 当前幂等请求最终生成的资源。第二阶段主要是 ticket。
    resource_type: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    resource_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)

    # 保存成功响应快照。后续可以用于完全复用原响应。
    response_body: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    # 过期时间。第二阶段只写入，不清理；后续可用后台任务清理。
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )
