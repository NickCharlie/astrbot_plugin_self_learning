"""
SQLAlchemy 数据库模型基类
"""
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase


class Base(AsyncAttrs, DeclarativeBase):
    """所有 ORM 模型的基类"""
    pass
