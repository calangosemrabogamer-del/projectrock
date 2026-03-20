@echo off
REM WordPress Scanner Launcher Script for Windows

title WordPress Username Detector and Scanner

echo ======================================
echo WordPress Username Detector and Scanner
echo ======================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo Error: Python is not installed
    echo Please install Python 3.7 or higher from python.org
    pause
    exit /b 1
)

REM Display Python version
echo Checking Python installation...
python --version
echo.

REM Navigate to script directory
cd /d "%~dp0"

REM Check and install dependencies
echo Checking dependencies...
python -c "import requests, bs4, urllib3" 2>nul
if errorlevel 1 (
    echo.
    echo Installing required dependencies...
    pip install -r requirements.txt
    
    if errorlevel 1 (
        echo.
        echo Error: Failed to install dependencies
        echo Please run manually: pip install -r requirements.txt
        pause
        exit /b 1
    )
)

echo.
echo All dependencies are installed!
echo Launching ProjectRock...
echo.

REM Prefer running built executable if available
if exist "dist\projectrock.exe" (
    dist\projectrock.exe
) else (
    python unified_scanner.py
)

REM Check exit status
if errorlevel 1 (
    echo.
    echo Application exited with an error
    echo Check logs for details
    pause
    exit /b 1
)
