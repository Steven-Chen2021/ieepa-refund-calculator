#!/bin/bash
set -e

# 定義預設路徑 (對應 Docker 內的配置)
FERNET_KEY_PATH=${FERNET_KEY_PATH:-"/app/data/keys/app_secret.key"}
DATA_ROOT=${DATA_ROOT:-"/app/data"}

# 1. 啟動 Redis 伺服器 (背景執行)
echo "Starting Redis server..."
redis-server --daemonize yes

# 2. 執行資料庫遷移
echo "Running database migrations..."
cd /app
alembic upgrade head

# 3. 初始化 Fernet 加密金鑰 (若不存在)
if [ ! -f "$FERNET_KEY_PATH" ]; then
    echo "Initializing Fernet encryption key: $FERNET_KEY_PATH"
    mkdir -p $(dirname "$FERNET_KEY_PATH")
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" > "$FERNET_KEY_PATH"
fi

# 4. 啟動 Celery Worker (背景執行)
echo "Starting Celery worker (OCR processor)..."
celery -A app.celery_app worker --loglevel=info &

# 5. 啟動 Nginx (背景執行)
echo "Starting Nginx..."
nginx -g "daemon on;"

# 6. 啟動 IEEPA API (前景執行)
echo "Starting IEEPA Refund Calculator API (Uvicorn)..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
