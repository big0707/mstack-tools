@echo off
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
if not exist ".venv\Scripts\python.exe" (
  echo Python environment missing. Run scripts\setup.ps1 first.
  exit /b 2
)
".venv\Scripts\python.exe" -m log_checker %*
exit /b %errorlevel%
