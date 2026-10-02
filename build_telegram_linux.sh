#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv .venv
fi
.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -e '.[dev,telegram]'
.venv/bin/python -m PyInstaller --noconfirm --clean --onefile --windowed \
  --name abie-telegram \
  --collect-all telethon \
  --collect-all dotenv \
  src/abie_gpt/telegram_desktop.py
echo "Built: dist/abie-telegram"
