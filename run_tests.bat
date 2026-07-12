@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
  echo [ERROR] 仮想環境がありません。.venvを作成してください。
  pause
  exit /b 1
)

call ".venv\Scripts\activate.bat"
python -m compileall . -q
if errorlevel 1 goto failed
pytest -q
if errorlevel 1 goto failed

echo [OK] すべてのテストが成功しました。
set "RESULT=0"
goto done

:failed
echo [ERROR] テストに失敗しました。
set "RESULT=1"

:done
pause
exit /b %RESULT%
