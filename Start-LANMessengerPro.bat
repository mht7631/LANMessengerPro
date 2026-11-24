@echo off
setlocal EnableExtensions
title LAN Messenger Pro
cd /d "%~dp0"

echo ================================================
echo          LAN Messenger Pro - Launcher
echo ================================================
echo.

REM Update source automatically when this folder is a Git checkout.
if exist ".git\" (
    where git >nul 2>nul
    if not errorlevel 1 (
        echo [1/4] Updating application source...
        git pull --ff-only origin main
        if errorlevel 1 (
            echo.
            echo ERROR: Update failed. Check your internet connection,
            echo Git installation, or local source changes.
            pause
            exit /b 1
        )
    ) else (
        echo [1/4] Git is not installed; using the source already in this folder.
    )
) else (
    echo [1/4] ZIP/source install detected; using the source already in this folder.
)

REM Find a supported Python 3 installation.
set "PYTHON_CMD="
where py >nul 2>nul
if not errorlevel 1 (
    py -3.13 --version >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=py -3.13"
    if not defined PYTHON_CMD (
        py -3.12 --version >nul 2>nul
        if not errorlevel 1 set "PYTHON_CMD=py -3.12"
    )
    if not defined PYTHON_CMD (
        py -3.11 --version >nul 2>nul
        if not errorlevel 1 set "PYTHON_CMD=py -3.11"
    )
)
if not defined PYTHON_CMD (
    where python >nul 2>nul
    if not errorlevel 1 (
        python -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)" >nul 2>nul
        if not errorlevel 1 set "PYTHON_CMD=python"
    )
)
if not defined PYTHON_CMD (
    echo.
    echo ERROR: Python 3.11 or newer was not found.
    echo Install Python 3.11+ from https://www.python.org/downloads/windows/
    echo During setup, enable the Python Launcher and Add Python to PATH.
    pause
    exit /b 1
)

REM Create an isolated environment once per project folder.
if not exist ".venv\Scripts\python.exe" (
    echo [2/4] Creating the virtual environment...
    %PYTHON_CMD% -m venv .venv
    if errorlevel 1 goto :failed
) else (
    echo [2/4] Virtual environment already exists.
)

REM Install/update project dependencies. This is needed on first launch
REM and whenever requirements change; the running messenger itself is LAN-only.
echo [3/4] Checking and installing required packages...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -e .
if errorlevel 1 goto :failed

echo [4/4] Starting LAN Messenger Pro...
echo.
".venv\Scripts\python.exe" -m lanmessenger
if errorlevel 1 goto :failed
exit /b 0

:failed
echo.
echo LAN Messenger Pro could not start. Review the error shown above.
echo First-time dependency installation requires internet access.
pause
exit /b 1