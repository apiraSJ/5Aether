@echo off
title Aether
cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
    echo ERROR: Virtual environment not found.
    echo Run setup.bat first.
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat
python -m aether %*
if errorlevel 1 pause
