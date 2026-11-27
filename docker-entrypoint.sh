#!/bin/sh
set -e
echo "[entrypoint] Chạy migration..."
for i in 1 2 3 4 5 6 7 8 9 10; do
  if alembic upgrade head; then break; fi
  echo "[entrypoint] DB chưa sẵn sàng, thử lại sau 3s ($i/10)"; sleep 3
done
echo "[entrypoint] Khởi động server"
# 1 process duy nhất: WebSocket hub + MQTT subscriber nằm trong bộ nhớ của process
exec uvicorn server.app:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips="*"
