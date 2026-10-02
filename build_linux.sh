#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [[ ! -x ".venv/bin/python" ]]; then
  echo "Virtual environment .venv not found."
  echo "Create it with: python3.11 -m venv .venv"
  exit 1
fi

source .venv/bin/activate
python -m pip install -e '.[dev]'
pyinstaller --noconfirm --clean --onefile --windowed \
  --name "abie-gpt" \
  --collect-all seleniumbase \
  --collect-all maxapi \
  --collect-all faster_whisper \
  --hidden-import=sqlalchemy.dialects.sqlite \
  src/abie_gpt/desktop.py

echo
echo "Linux executable: dist/abie-gpt"
