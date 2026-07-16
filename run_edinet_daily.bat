@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Python virtual environment was not found.
  echo Run: python -m venv .venv
  exit /b 2
)

call ".venv\Scripts\activate.bat"
python "scripts\fetch_edinet.py" --preset daily
set EXIT_CODE=%ERRORLEVEL%

echo.
echo EDINET daily fetch finished with exit code %EXIT_CODE%.
exit /b %EXIT_CODE%
