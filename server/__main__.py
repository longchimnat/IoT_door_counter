"""Chạy server: python -m server [--reload] [--host 0.0.0.0] [--port 8000]

Trên Windows uvicorn mặc định dùng ProactorEventLoop - paho/aiomqtt không chạy được trên loop này,
nên ở đây ép dùng SelectorEventLoop để MQTT hoạt động.
"""
from __future__ import annotations

import argparse
import asyncio
import sys

import uvicorn

from .config import get_settings


def selector_loop_factory() -> asyncio.AbstractEventLoop:
    """Loop factory cho uvicorn (--loop server.__main__:selector_loop_factory): trả về 1 event loop mới."""
    return asyncio.SelectorEventLoop()


def main() -> None:
    s = get_settings()
    p = argparse.ArgumentParser(description="IoT De tai 2 backend")
    p.add_argument("--host", default=s.host)
    p.add_argument("--port", type=int, default=s.port)
    p.add_argument("--reload", action="store_true", help="tự khởi động lại khi sửa code (dev)")
    args = p.parse_args()

    uvicorn.run(
        "server.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        reload_dirs=["server"] if args.reload else None,
        log_level=s.log_level.lower(),
        loop="server.__main__:selector_loop_factory" if sys.platform == "win32" else "auto",
        proxy_headers=True,
        forwarded_allow_ips="*",
    )


if __name__ == "__main__":
    main()
