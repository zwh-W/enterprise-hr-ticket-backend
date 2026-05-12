from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictException, UnauthorizedException
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.repositories.user_repo import UserRepository
from app.schemas.auth import LoginRequest, RegisterRequest, Token


class AuthService:
    @staticmethod
    def register(db: Session, payload: RegisterRequest) -> User:
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
        user = UserRepository.get_by_email(db, email)
        if not user or not verify_password(password, user.hashed_password):
            raise UnauthorizedException(message="Invalid email or password.")
        if not user.is_active:
            raise UnauthorizedException(message="User is inactive.")
        return user

    @staticmethod
    def _issue_token(user: User) -> Token:
        token = create_access_token(
            subject=str(user.id),
            extra_claims={"role": user.role.value},
        )
        return Token(access_token=token)

    @staticmethod
    def login(db: Session, payload: LoginRequest) -> Token:
        user = AuthService.authenticate(db, payload.email, payload.password)
        return AuthService._issue_token(user)

    @staticmethod
    def login_with_credentials(db: Session, email: str, password: str) -> Token:
        user = AuthService.authenticate(db, email, password)
        return AuthService._issue_token(user)
