#!/usr/bin/env bash
# Chạy server dev (Linux / macOS / Raspberry Pi): ./run_dev.sh
set -e
cd "$(dirname "$0")"
if [ ! -d .venv ]; then python3 -m venv .venv; fi
source .venv/bin/activate
pip install -q -r requirements-dev.txt
[ -f .env ] || cp .env.example .env
alembic upgrade head
python -m server --reload
