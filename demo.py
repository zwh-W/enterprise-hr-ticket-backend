from fastapi import FastAPI, Depends, HTTPException, Header
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session


# ==========================================
# 1. 配置管家：自动读取同目录下的 .env 文件
# ==========================================
class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    INTERNAL_API_KEY: str

    # 魔法开关：告诉 Pydantic 去哪里找配置
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()

# ==========================================
# 2. 数据库流水线 (直连你的 PostgreSQL)
# ==========================================
engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ==========================================
# 3. Agent 鉴权锁 (拦截 X-Internal-API-Key)
# ==========================================
def verify_internal_api_key(
        # Header(alias=...) 意思是：哪怕前端传的是 X-Internal-API-Key (带连字符)，
        # 到 Python 里也能优雅地变成 x_internal_api_key 变量
        x_internal_api_key: str = Header(alias="X-Internal-API-Key")
):
    # 严格比对请求头里的 key 和 .env 里的 key
    if x_internal_api_key != settings.INTERNAL_API_KEY:
        raise HTTPException(status_code=401, detail="Agent Auth Failed: Invalid API Key")
    return x_internal_api_key


# ==========================================
# 4. FastAPI 路由
# ==========================================
app = FastAPI()


# 测试接口：验证数据库连通性
@app.get("/system/status")
async def check_db_status(db: Session = Depends(get_db)):
    result = db.execute(text("SELECT 1")).scalar()
    return {"database_alive": result == 1}


@app.post("/internal/tickets/mock")
def mock_agent_create_ticket(
        db:Session = Depends(get_db),
        api_key: str=Depends(verify_internal_api_key)
):
    # 无需真实写入逻辑，直接返回成功结果
    return {
        "msg": "工单创建成功",
        "db_connected": True
    }
