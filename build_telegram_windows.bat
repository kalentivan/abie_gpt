@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  py -3 -m venv .venv
)
.venv\Scripts\python.exe -m pip install -U pip
.venv\Scripts\python.exe -m pip install -e ".[dev,telegram]"
.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name abie-telegram ^
  --collect-all telethon ^
  --collect-all dotenv ^
  src\abie_gpt\telegram_desktop.py
echo Built: dist\abie-telegram.exe
