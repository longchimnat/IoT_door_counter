"""Quản lý thiết bị (dành cho dashboard, cần JWT)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..models import Device, User
from ..schemas import DeviceCreate, DeviceOut, DeviceUpdate, DeviceWithKey
from ..security import generate_api_key, get_current_user

router = APIRouter(prefix="/api/v1/devices", tags=["devices"])


async def get_device_or_404(session: AsyncSession, device_id: int) -> Device:
    device = await session.get(Device, device_id)
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Không tìm thấy thiết bị id={device_id}")
    return device


@router.get("", response_model=list[DeviceOut])
async def list_devices(session: AsyncSession = Depends(get_session), _: User = Depends(get_current_user)):
    return (await session.scalars(select(Device).order_by(Device.id))).all()


@router.post("", response_model=DeviceWithKey, status_code=status.HTTP_201_CREATED)
async def create_device(body: DeviceCreate, session: AsyncSession = Depends(get_session), _: User = Depends(get_current_user)):
    device = Device(device_uid=body.device_uid, name=body.name, location=body.location, api_key=generate_api_key())
    session.add(device)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, f"device_uid '{body.device_uid}' đã tồn tại")
    await session.refresh(device)
    return device


@router.get("/{device_id}", response_model=DeviceWithKey)
async def get_device(device_id: int, session: AsyncSession = Depends(get_session), _: User = Depends(get_current_user)):
    return await get_device_or_404(session, device_id)


@router.patch("/{device_id}", response_model=DeviceOut)
async def update_device(
    device_id: int, body: DeviceUpdate, session: AsyncSession = Depends(get_session), _: User = Depends(get_current_user)
):
    device = await get_device_or_404(session, device_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(device, k, v)
    await session.commit()
    await session.refresh(device)
    return device


@router.post("/{device_id}/rotate-key", response_model=DeviceWithKey)
async def rotate_key(device_id: int, session: AsyncSession = Depends(get_session), _: User = Depends(get_current_user)):
    device = await get_device_or_404(session, device_id)
    device.api_key = generate_api_key()
    await session.commit()
    await session.refresh(device)
    return device


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device(device_id: int, session: AsyncSession = Depends(get_session), _: User = Depends(get_current_user)):
    device = await get_device_or_404(session, device_id)
    await session.delete(device)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
