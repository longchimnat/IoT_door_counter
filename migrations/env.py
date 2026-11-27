"""Alembic env - lấy DATABASE_URL từ server.config (file .env / biến môi trường)."""
import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server import models  # noqa: E402,F401  (đăng ký bảng)
from server.config import get_settings  # noqa: E402
from server.database import Base, UTCDateTime  # noqa: E402

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)
target_metadata = Base.metadata

if settings.is_sqlite:  # tạo thư mục data/ nếu chưa có
    db_path = settings.database_url.split(":///", 1)[-1]
    if db_path and db_path != ":memory:":
        Path(db_path).resolve().parent.mkdir(parents=True, exist_ok=True)


def render_item(type_, obj, autogen_context):
    """Ghi kiểu UTCDateTime ra migration dưới dạng sa.DateTime(timezone=True)."""
    if type_ == "type" and isinstance(obj, UTCDateTime):
        return "sa.DateTime(timezone=True)"
    return False


def _configure(**kw):
    context.configure(
        target_metadata=target_metadata,
        render_item=render_item,
        render_as_batch=settings.is_sqlite,  # SQLite cần batch mode để ALTER TABLE
        compare_type=True,
        **kw,
    )


def run_migrations_offline() -> None:
    _configure(url=config.get_main_option("sqlalchemy.url"), literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    _configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
