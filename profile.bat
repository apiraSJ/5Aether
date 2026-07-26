@echo off
REM Aether Performance Profiler — Run on target hardware
REM Collects 60-second baseline, then prints report
REM
REM Usage:
REM   profile.bat              60 seconds
REM   profile.bat 30           30 seconds
REM   profile.bat 120          2 minutes
REM
REM The report will appear in terminal AND be saved to profile_results.txt

setlocal

set DURATION=%1
if "%DURATION%"=="" set DURATION=60

echo ========================================================
echo   Aether Performance Profiler
echo   Duration: %DURATION% seconds
echo ========================================================
echo.

REM Ensure we're in project root
cd /d "%~dp0"

REM Ensure venv exists
if not exist ".venv\Scripts\python.exe" (
    echo [!] Virtual environment not found. Run setup.bat first.
    exit /b 1
)

echo Running profiler for %DURATION% seconds...
echo Press Ctrl+C to stop early (report still prints)
echo.

".venv\Scripts\python.exe" -m aether --mode vision --profile --duration %DURATION% 2>&1

echo.
echo ========================================================
echo   Profiler complete
echo ========================================================

pause
