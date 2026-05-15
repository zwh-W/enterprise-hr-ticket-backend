"""Repository for idempotency_keys.

Repository 层只负责数据库读写，不写业务决策。
是否允许复用响应、是否拒绝请求体不一致，放在 service 层处理。
"""

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.idempotency import IdempotencyKey, IdempotencyStatus


class IdempotencyRepository:
    """幂等表数据库访问对象。"""

    @staticmethod
    def get_by_key(db: Session, key: str) -> IdempotencyKey | None:
        """通过幂等键查询记录。"""
        stmt = select(IdempotencyKey).where(IdempotencyKey.key == key)
        return db.scalar(stmt)

    @staticmethod
    def create_processing(
        db: Session,
        *,
        key: str,
        request_hash: str,
        expires_at: datetime | None,
    ) -> IdempotencyKey:
        """创建 processing 状态的幂等记录。

        业务操作开始前先登记 key，确保同一个 key 不能并发创建多个资源。
        """
        item = IdempotencyKey(
            key=key,
            request_hash=request_hash,
            status=IdempotencyStatus.processing,
            expires_at=expires_at,
        )
        db.add(item)
        db.flush()
        return item

    @staticmethod
    def mark_succeeded(
        db: Session,
        item: IdempotencyKey,
        *,
        resource_type: str,
        resource_id: str,
        response_body: dict[str, Any],
    ) -> IdempotencyKey:
        """把幂等记录标记为成功，并保存资源引用和响应快照。"""
        item.status = IdempotencyStatus.succeeded
        item.resource_type = resource_type
        item.resource_id = resource_id
        item.response_body = response_body
        db.add(item)
        db.flush()
        return item

    @staticmethod
    def mark_failed(db: Session, item: IdempotencyKey) -> IdempotencyKey:
        """把幂等记录标记为失败。第二阶段暂时很少使用，预留给后续重试策略。"""
        item.status = IdempotencyStatus.failed
        db.add(item)
        db.flush()
        return item
