@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\activate.bat" echo [ERROR] 仮想環境がありません。 & pause & exit /b 1
call ".venv\Scripts\activate.bat"
pytest -q tests\ui
set "RESULT=%ERRORLEVEL%"
if "%RESULT%"=="0" (echo [OK] UIテストが成功しました。) else (echo [ERROR] UIテストに失敗しました。)
pause
exit /b %RESULT%
