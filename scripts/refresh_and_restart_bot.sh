#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo "==> Обновляем токен через refresh_jwt.sh"
./scripts/refresh_jwt.sh

echo "==> Останавливаем запущенный telegram_bot.py (если он работает)"
if pgrep -f "python.*telegram_bot.py" >/dev/null 2>&1; then
  pkill -f "python.*telegram_bot.py"
  sleep 2
fi

if command -v uv >/dev/null 2>&1; then
  START_CMD=("uv" "run" "python" "telegram_bot.py")
else
  START_CMD=("python" "telegram_bot.py")
fi

echo "==> Запускаем telegram_bot.py в текущем терминале"
exec "${START_CMD[@]}"