@echo off
setlocal

set "ROOT_DIR=%~dp0"

if exist "%ROOT_DIR%.venv\Scripts\python.exe" (
  "%ROOT_DIR%.venv\Scripts\python.exe" "%ROOT_DIR%run.py" %*
  exit /b %errorlevel%
)

where py >nul 2>nul
if %errorlevel%==0 (
  py -3 "%ROOT_DIR%run.py" %*
  exit /b %errorlevel%
)

where python >nul 2>nul
if %errorlevel%==0 (
  python "%ROOT_DIR%run.py" %*
  exit /b %errorlevel%
)

echo Python 3.11+ not found. Please install Python first.
exit /b 1
