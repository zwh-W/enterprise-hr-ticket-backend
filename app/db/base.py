"""SQLAlchemy declarative base.

这个文件只定义 Base，不导入任何模型。
原因：模型文件会导入 Base；如果 Base 再导入模型，就会形成循环导入。
Alembic 需要发现模型时，由 alembic/env.py 主动 import app.models。
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """所有 ORM Model 的基类。"""

    pass
