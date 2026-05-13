"""Authentication HTTP routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.auth import LoginRequest, RegisterRequest, Token
from app.schemas.user import UserRead
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    """注册用户。"""
    return AuthService.register(db, payload)


@router.post("/login", response_model=Token)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    """JSON 登录接口，适合前端、Postman、脚本调用。"""
    return AuthService.login(db, payload)


@router.post("/token", response_model=Token)
def login_for_swagger(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Session = Depends(get_db),
):
    """Swagger UI Authorize 使用的表单登录接口。

    OAuth2PasswordRequestForm 固定字段名为 username/password。
    本项目把 username 当作 email。
    """
    return AuthService.login_with_credentials(db=db, email=form_data.username, password=form_data.password)
