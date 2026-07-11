@echo off
setlocal

cd /d "%~dp0"
set STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

echo ========================================
echo Starting Orekabu AI
echo ========================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo Python was not found.
    echo Please install Python 3.11 or later, then run this file again.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo Failed to create virtual environment.
        pause
        exit /b 1
    )
)

call ".venv\Scripts\activate.bat"

echo Upgrading pip...
python -m pip install --upgrade pip
if errorlevel 1 (
    echo Failed to upgrade pip.
    pause
    exit /b 1
)

echo Installing requirements...
pip install -r requirements.txt
if errorlevel 1 (
    echo Failed to install requirements.
    pause
    exit /b 1
)

echo.
echo Open this URL in your browser:
echo http://localhost:8501
echo.
echo To stop the app, press Ctrl+C in this window.
echo.

python -m streamlit run app.py --browser.gatherUsageStats false

pause
