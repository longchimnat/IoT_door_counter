"""FastAPI app - Đề tài 2: Đếm lượt người qua cửa.

Chạy dev:   uvicorn server.app:app --reload        (hoặc: python -m server --reload)
Swagger:    http://localhost:8000/docs
Dashboard:  http://localhost:8000/
"""
from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from .config import get_settings
from .database import create_all, dispose_engine, get_engine, init_engine
from .mqtt.bridge import bridge
from .routers import alerts, auth, control, device_api, devices, stats, ws
from .seed import seed
from .services.device_service import offline_monitor
from .services.realtime import hub

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
log = logging.getLogger("server")


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    _setup_logging(s.log_level)
    init_engine(s.database_url, echo=s.db_echo)
    if s.auto_create_tables:
        await create_all()
    await seed()
    if s.jwt_secret.startswith("change-me") and s.environment == "production":
        log.warning("JWT_SECRET đang dùng giá trị mặc định - hãy đổi trong .env!")

    stop = asyncio.Event()
    monitor = asyncio.create_task(offline_monitor(stop), name="offline-monitor")
    bridge.start()
    log.info("Server sẵn sàng - DB: %s | MQTT: %s", s.database_url.split("@")[-1], "bật" if s.mqtt_enabled else "tắt")
    try:
        yield
    finally:
        stop.set()
        await bridge.stop()
        try:
            await asyncio.wait_for(monitor, timeout=5)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            monitor.cancel()
        await dispose_engine()


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title=s.app_name,
        version="1.0.0",
        description="Backend đề tài 2 - Đếm lượt người qua cửa (Raspberry Pi + HC-SR04 + PIR).",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origin_list or ["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def access_log(request: Request, call_next):
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            log.exception("Lỗi không xử lý được: %s %s", request.method, request.url.path)
            return JSONResponse({"detail": "Lỗi máy chủ nội bộ"}, status_code=500)
        if request.url.path.startswith("/api/"):
            log.info("%s %s -> %d (%.0f ms)", request.method, request.url.path, response.status_code, (time.perf_counter() - start) * 1000)
        return response

    @app.get("/health", tags=["health"])
    async def health():
        db_ok = True
        try:
            async with get_engine().connect() as conn:
                await conn.execute(text("SELECT 1"))
        except Exception:
            db_ok = False
        return JSONResponse(
            {"status": "ok" if db_ok else "degraded", "database": db_ok, "mqtt_enabled": s.mqtt_enabled,
             "mqtt_connected": bridge.connected, "ws_clients": hub.client_count},
            status_code=200 if db_ok else 503,
        )

    for r in (auth.router, devices.router, control.router, device_api.router, stats.router, alerts.router, ws.router):
        app.include_router(r)

    if WEB_DIR.is_dir():
        app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
    return app


app = create_app()
