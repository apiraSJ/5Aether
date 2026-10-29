@echo off
setlocal EnableDelayedExpansion
title Aether Mark-1 Web Launcher

cd /d "%~dp0"

echo ========================================
echo       Aether Mark-1 Web Launcher
echo ========================================
echo.

REM --- Locate a compatible Python interpreter ---
set "PY="
where python >nul 2>&1
if %errorlevel%==0 set "PY=python"
if not defined PY (
    where py >nul 2>&1
    if %errorlevel%==0 set "PY=py -3"
)
if not defined PY (
    echo ERROR: Python 3.12+ was not found on PATH.
    echo Install Python from https://www.python.org/downloads/ and re-run this launcher.
    pause
    exit /b 1
)

set "VENV_PY=%~dp0.venv\Scripts\python.exe"

REM --- First-run bootstrap: create .venv if missing ---
if not exist "%VENV_PY%" (
    echo [setup] Creating virtual environment...
    %PY% -m venv "%~dp0.venv"
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment.
        pause
        exit /b 1
    )
)

REM --- Install Web Mode dependencies when missing ---
"%VENV_PY%" -c "import fastapi, uvicorn" >nul 2>&1
if errorlevel 1 (
    echo [setup] Installing Web Mode dependencies...
    "%VENV_PY%" -m pip install -e "%~dp0.[server]"
    if errorlevel 1 (
        echo ERROR: Dependency installation failed.
        pause
        exit /b 1
    )
)

REM --- Safely stop any existing Aether backend on port 8765 ---
set "STOP_PS=%~dp0tools\stop_aether.ps1"
if exist "%STOP_PS%" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%STOP_PS%" -Port 8765 -Force >nul 2>&1
)

echo [1/3] Starting Aether Mark-1 Backend (--mode web)...
start "Aether Mark-1 Backend" cmd /k ""%VENV_PY%" -m aether --mode web"

echo [2/3] Waiting for server to boot (approx. 5 seconds)...
powershell -Command "Start-Sleep -Seconds 5" >nul 2>&1

powershell -Command "Invoke-WebRequest -Uri 'http://127.0.0.1:8765/health' -UseBasicParsing -TimeoutSec 3" >nul 2>&1
if errorlevel 1 (
    echo    [WARNING] Health check not yet responding - opening browser anyway.
)

echo [3/3] Opening Mark-1 Web at http://127.0.0.1:8765/
start "" "http://127.0.0.1:8765/"
echo.
echo Mark-1 launch sequence completed.
exit /b 0
