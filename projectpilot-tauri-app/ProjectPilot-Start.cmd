@echo off
setlocal

set "ROOT=%~dp0"
set "PYTHON_EXE=%ROOT%.venv\Scripts\python.exe"

if not exist "%PYTHON_EXE%" (
  set "PYTHON_EXE=python"
)

echo Starting ProjectPilot backend...
start "ProjectPilot Backend" /D "%ROOT%backend" cmd /k ""%PYTHON_EXE%" -m uvicorn main:app --host 127.0.0.1 --port 8000"

timeout /t 3 /nobreak >nul

if exist "%ROOT%src-tauri\target\release\projectpilot.exe" (
  echo Opening ProjectPilot desktop app...
  start "" "%ROOT%src-tauri\target\release\projectpilot.exe"
  exit /b 0
)

if exist "%ROOT%src-tauri\target\debug\projectpilot.exe" (
  echo Opening ProjectPilot debug desktop app...
  start "" "%ROOT%src-tauri\target\debug\projectpilot.exe"
  exit /b 0
)

echo Desktop executable was not found. Starting Tauri dev mode...
npm run tauri:dev
