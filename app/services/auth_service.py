"""Authentication service.

Service 层负责认证业务逻辑：注册、密码校验、JWT 签发。
Router 层只负责接收 HTTP 请求，不直接处理密码和 token。
"""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictException, UnauthorizedException
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.repositories.user_repo import UserRepository
from app.schemas.auth import LoginRequest, RegisterRequest, Token


class AuthService:
    """认证业务服务。"""

    @staticmethod
    def register(db: Session, payload: RegisterRequest) -> User:
        """注册用户。

        密码必须 hash 后才能入库；不能保存明文密码。
        """
        existing = UserRepository.get_by_email(db, payload.email)
        if existing:
            raise ConflictException(message="Email already registered.")

        try:
            user = UserRepository.create(
                db,
                email=payload.email,
                username=payload.username,
                hashed_password=hash_password(payload.password),
                role=payload.role,
            )
            db.commit()
            db.refresh(user)
            return user
        except IntegrityError as exc:
            db.rollback()
            raise ConflictException(message="Email already registered.") from exc
        except Exception:
            db.rollback()
            raise

    @staticmethod
    def authenticate(db: Session, email: str, password: str) -> User:
        """校验邮箱和密码，返回合法用户。"""
        user = UserRepository.get_by_email(db, email)
        if not user or not verify_password(password, user.hashed_password):
            raise UnauthorizedException(message="Invalid email or password.")
        if not user.is_active:
            raise UnauthorizedException(message="User is inactive.")
        return user

    @staticmethod
    def _issue_token(user: User) -> Token:
        """签发 JWT。

        sub 存用户 ID，role 作为额外声明，方便后续排查 token 内容。
        真正权限判断仍然以数据库中的用户角色为准。
        """
        token = create_access_token(subject=str(user.id), extra_claims={"role": user.role.value})
        return Token(access_token=token)

    @staticmethod
    def login(db: Session, payload: LoginRequest) -> Token:
        """JSON 登录接口使用的登录方法。"""
        user = AuthService.authenticate(db, payload.email, payload.password)
        return AuthService._issue_token(user)

    @staticmethod
    def login_with_credentials(db: Session, email: str, password: str) -> Token:
        """Swagger OAuth2 password flow 使用的登录方法。

        Swagger 的字段名叫 username，但本系统实际把它当 email 使用。
        """
        user = AuthService.authenticate(db, email, password)
        return AuthService._issue_token(user)
