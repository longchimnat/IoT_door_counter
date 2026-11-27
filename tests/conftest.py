from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DEVICE_KEY = "test-device-key"


def _reset_database(url: str) -> None:
    """Xóa sạch bảng trên DB thật (PostgreSQL) trước mỗi test."""
    import asyncio

    from sqlalchemy.ext.asyncio import create_async_engine

    from server import models  # noqa: F401
    from server.database import Base

    async def run() -> None:
        engine = create_async_engine(url)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()

    asyncio.run(run())


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """TestClient với CSDL SQLite riêng cho mỗi test."""
    # Mặc định SQLite tạm; đặt TEST_DATABASE_URL=postgresql+asyncpg://... để test trên PostgreSQL
    db_url = os.environ.get("TEST_DATABASE_URL") or f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}"
    if not db_url.startswith("sqlite"):
        _reset_database(db_url)
    env = {
        "DATABASE_URL": db_url,
        "AUTO_CREATE_TABLES": "true",
        "ADMIN_USERNAME": "admin",
        "ADMIN_PASSWORD": "secret123",
        "JWT_SECRET": "test-secret-0123456789-0123456789-abcdef",
        "DEFAULT_DEVICE_UID": "door-01",
        "DEFAULT_DEVICE_API_KEY": DEVICE_KEY,
        "MQTT_ENABLED": "false",
        "SERVER_DEBOUNCE_SECONDS": "1.0",
        "TIMEZONE": "Asia/Ho_Chi_Minh",
        "LOG_LEVEL": "WARNING",
    }
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.chdir(tmp_path)  # không đọc file .env của dự án

    from server.config import get_settings

    get_settings.cache_clear()
    from fastapi.testclient import TestClient

    from server.app import create_app

    with TestClient(create_app()) as c:
        yield c
    get_settings.cache_clear()


@pytest.fixture()
def token(client) -> str:
    r = client.post("/api/v1/auth/login", json={"username": "admin", "password": "secret123"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture()
def auth(token) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def dev() -> dict:
    return {"X-API-Key": DEVICE_KEY}


@pytest.fixture()
def device_id(client, auth) -> int:
    r = client.get("/api/v1/devices", headers=auth)
    assert r.status_code == 200
    return next(d["id"] for d in r.json() if d["device_uid"] == "door-01")
