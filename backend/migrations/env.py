"""Alembic 迁移环境。

使用方式:
  cd backend
  alembic upgrade head                     # 应用所有迁移
  alembic revision -m "xxx"                # 新增空迁移（手写变更）
生成新迁移前先用 alembic stamp 0001_baseline 标记基线（若库已存在）。
"""
from logging.config import fileConfig

from alembic import context

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 目标库：默认 backend/data/financecrew.db，可用 DATABASE_URL 覆盖
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sqlalchemy import create_engine

db_path = os.environ.get("FC_DB_PATH", Path(__file__).resolve().parent.parent / "data" / "financecrew.db")
url = os.environ.get("DATABASE_URL", f"sqlite:///{db_path}")
target_metadata = None  # 项目未使用 SQLAlchemy 模型，迁移以手写 SQL 为主


def run_migrations_offline() -> None:
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(url, future=True)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
