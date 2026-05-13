"""Pytest shared fixtures.

测试环境使用 SQLite in-memory，避免依赖真实 PostgreSQL。
注意：这适合第一阶段/第二阶段接口测试；如果要验证 PostgreSQL 特性，后续可换 testcontainers。
"""

import os

# 必须在导入 app.main 之前设置环境变量，否则 Settings 可能已经被缓存。
os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["JWT_SECRET_KEY"] = "test-secret"
os.environ["INTERNAL_API_KEY"] = "test-internal-key"
os.environ["IDEMPOTENCY_KEY_TTL_HOURS"] = "24"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.core.config import get_settings
from app.db.base import Base
from app.main import app

# 清理 Settings 缓存，确保测试环境变量生效。
get_settings.cache_clear()

engine = create_engine(
    "sqlite+pysqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, class_=Session, autoflush=False, autocommit=False, expire_on_commit=False)


def override_get_db():
    """替换 FastAPI 里的数据库依赖，使测试走内存数据库。"""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def setup_database():
    """每个测试前重建表，保证测试之间互不污染。"""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client() -> TestClient:
    """FastAPI 测试客户端。"""
    return TestClient(app)


def register_user(client: TestClient, *, email: str, username: str, password: str = "Password123!", role: str = "employee"):
    """注册测试用户。"""
    return client.post(
        "/auth/register",
        json={"email": email, "username": username, "password": password, "role": role},
    )


def login_user(client: TestClient, *, email: str, password: str = "Password123!") -> str:
    """登录测试用户并返回 access_token。"""
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def auth_headers(token: str) -> dict[str, str]:
    """生成认证请求头。"""
    return {"Authorization": f"Bearer {token}"}
