"""Tạo dữ liệu khởi đầu: tài khoản admin và thiết bị mặc định (idempotent)."""
from __future__ import annotations

import logging

from sqlalchemy import select

from .config import get_settings
from .database import get_sessionmaker
from .models import Device, User
from .security import hash_password

log = logging.getLogger(__name__)


async def seed() -> None:
    s = get_settings()
    async with get_sessionmaker()() as session:
        if s.admin_username:
            user = await session.scalar(select(User).where(User.username == s.admin_username))
            if user is None:
                session.add(User(username=s.admin_username, password_hash=hash_password(s.admin_password), full_name="Administrator"))
                log.info("Seed: tạo tài khoản '%s'", s.admin_username)

        if s.default_device_uid:
            device = await session.scalar(select(Device).where(Device.device_uid == s.default_device_uid))
            if device is None:
                session.add(
                    Device(
                        device_uid=s.default_device_uid,
                        name=s.default_device_name,
                        location=s.default_device_location,
                        api_key=s.default_device_api_key,
                    )
                )
                log.info("Seed: tạo thiết bị '%s'", s.default_device_uid)
        await session.commit()


if __name__ == "__main__":  # python -m server.seed
    import asyncio

    from .database import dispose_engine, init_engine

    async def _main() -> None:
        init_engine(get_settings().database_url)
        await seed()
        await dispose_engine()

    logging.basicConfig(level=logging.INFO)
    asyncio.run(_main())
