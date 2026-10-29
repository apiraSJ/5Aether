@echo off
setlocal EnableDelayedExpansion
title Aether Mark-1 Stop
cd /d "%~dp0"

echo ========================================
echo       Aether Mark-1 Stop (safe)
echo ========================================
echo.

set "PS=%~dp0tools\stop_aether.ps1"
if not exist "%PS%" (
    echo ERROR: Cannot find stop script at "%PS%"
    pause
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%PS%" -Force
set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="0" (
    echo Stop sequence completed.
) else if "%RC%"=="1" (
    echo Stop was NOT performed (see messages above). No unrelated process was killed.
) else (
    echo Stop encountered an unexpected error.
)
echo.
pause
exit /b %RC%