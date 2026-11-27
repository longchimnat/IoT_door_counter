"""Xác thực: JWT cho người dùng dashboard, API key cho thiết bị."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import timedelta

import jwt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_settings
from .database import get_session, utcnow
from .models import Device, User

_PBKDF2_ITERATIONS = 240_000
_bearer = HTTPBearer(auto_error=False)


# ---------- Password (PBKDF2-SHA256, chỉ dùng thư viện chuẩn) ----------
def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ITERATIONS)
    return "pbkdf2_sha256${}${}${}".format(
        _PBKDF2_ITERATIONS, base64.b64encode(salt).decode(), base64.b64encode(dk).decode()
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt_b64, hash_b64 = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, int(iterations))
        return hmac.compare_digest(dk, expected)
    except (ValueError, TypeError):
        return False


def generate_api_key() -> str:
    return secrets.token_urlsafe(32)


# ---------- JWT ----------
def create_access_token(username: str) -> tuple[str, int]:
    s = get_settings()
    expires = timedelta(minutes=s.jwt_expire_minutes)
    now = utcnow()
    payload = {"sub": username, "iat": now, "exp": now + expires, "typ": "access"}
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm), int(expires.total_seconds())


def decode_token(token: str) -> str:
    s = get_settings()
    try:
        payload = jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token đã hết hạn", headers={"WWW-Authenticate": "Bearer"})
    except jwt.InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token không hợp lệ", headers={"WWW-Authenticate": "Bearer"})
    sub = payload.get("sub")
    if not sub or payload.get("typ") != "access":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token không hợp lệ", headers={"WWW-Authenticate": "Bearer"})
    return sub


async def user_from_token(token: str, session: AsyncSession) -> User:
    username = decode_token(token)
    user = await session.scalar(select(User).where(User.username == username))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Tài khoản không tồn tại hoặc bị khóa")
    return user


# ---------- Dependencies ----------
async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_session),
) -> User:
    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Thiếu Bearer token", headers={"WWW-Authenticate": "Bearer"})
    return await user_from_token(creds.credentials, session)


async def get_current_device(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    session: AsyncSession = Depends(get_session),
) -> Device:
    if not x_api_key:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Thiếu header X-API-Key")
    device = await session.scalar(select(Device).where(Device.api_key == x_api_key))
    if device is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "API key không hợp lệ")
    return device
