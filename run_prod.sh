#!/usr/bin/env bash
# Chạy server production không dùng Docker (vd. ngay trên Raspberry Pi): ./run_prod.sh
set -e
cd "$(dirname "$0")"
if [ ! -d .venv ]; then python3 -m venv .venv; fi
source .venv/bin/activate
pip install -q -r requirements.txt
[ -f .env ] || cp .env.example .env
alembic upgrade head
# 1 process: WebSocket hub + MQTT subscriber nằm trong bộ nhớ của process
exec uvicorn server.app:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips="*"
