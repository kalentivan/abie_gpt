@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Virtual environment .venv not found.
  exit /b 1
)
call .venv\Scripts\activate.bat
python -m pip install -e ".[dev]"
pyinstaller --noconfirm --clean --onefile --windowed --name "ABIE GPT" ^
  --collect-all seleniumbase ^
  --collect-all maxapi ^
  --collect-all faster_whisper ^
  --hidden-import=sqlalchemy.dialects.sqlite ^
  src\abie_gpt\desktop.py
echo.
echo EXE: dist\ABIE GPT.exe
