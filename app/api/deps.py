"""FastAPI dependency functions.

deps.py 放通用依赖：数据库 Session、当前用户解析、角色限制、Internal API Key 校验。
具体业务权限仍然应该放在 service 层，例如“employee 是否能看某张 ticket”。
"""

import uuid
from collections.abc import Generator
from typing import Annotated, Callable

from fastapi import Depends, Header
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import ForbiddenException, UnauthorizedException
from app.core.security import decode_access_token
from app.db.session import SessionLocal
from app.models.user import User, UserRole
from app.repositories.user_repo import UserRepository

# Swagger Authorize 使用 /auth/token 表单登录。
# /auth/login 保留 JSON 登录，适合前端和脚本调用。
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


def get_db() -> Generator[Session, None, None]:
    """为每个请求创建一个数据库 Session。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    """从 Authorization Bearer token 中解析当前用户。"""
    payload = decode_access_token(token)
    subject = payload.get("sub")

    try:
        user_id = uuid.UUID(str(subject))
    except ValueError as exc:
        raise UnauthorizedException(message="Invalid access token subject.") from exc

    user = UserRepository.get_by_id(db, user_id)
    if not user:
        raise UnauthorizedException(message="User not found.")
    return user


def get_current_active_user(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    """确保当前用户未被禁用。"""
    if not current_user.is_active:
        raise UnauthorizedException(message="User is inactive.")
    return current_user


def require_roles(*allowed_roles: UserRole) -> Callable[..., User]:
    """生成一个角色依赖，用于 admin-only / hr-only 等接口。"""

    def dependency(current_user: Annotated[User, Depends(get_current_active_user)]) -> User:
        if current_user.role not in set(allowed_roles):
            allowed = ", ".join(role.value for role in allowed_roles)
            raise ForbiddenException(message=f"Required role: {allowed}.")
        return current_user

    return dependency


def verify_internal_api_key(
    x_internal_api_key: Annotated[str | None, Header(alias="X-Internal-API-Key")] = None,
) -> None:
    """校验 Internal API Key。

    Internal API 是服务间调用，不使用用户 JWT。
    这个依赖只负责校验调用方是否持有内部密钥。
    """
    settings = get_settings()
    if not x_internal_api_key or x_internal_api_key != settings.internal_api_key:
        raise UnauthorizedException(message="Invalid internal API key.")
