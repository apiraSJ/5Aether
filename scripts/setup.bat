@echo off
title Aether Setup
echo ============================================================
echo   Aether — First-Time Setup
echo ============================================================
echo.

cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found in PATH.
    echo Install Python 3.12+ from https://python.org
    pause
    exit /b 1
)

echo [1/3] Creating virtual environment...
if not exist ".venv" (
    python -m venv .venv
    echo       Done.
) else (
    echo       .venv already exists, skipping.
)

echo.
echo [2/3] Activating venv...
call .venv\Scripts\activate.bat

echo.
echo [3/3] Installing Aether...
pip install -e ".[full]" -q
if errorlevel 1 (
    echo.
    echo Retrying with minimal deps...
    pip install -e . -q
)

echo.
echo ============================================================
echo   Setup complete!
echo.
echo   To start Aether:
echo     start.bat
echo.
echo   Or manually:
echo     .venv\Scripts\activate
echo     python -m aether
echo ============================================================
echo.
pause
