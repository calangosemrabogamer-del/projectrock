@echo off
REM Build script for ProjectRock executable (Windows)

setlocal enabledelayedexpansion

REM Ensure we are in project directory
cd /d "%~dp0"

REM Ensure Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo Error: Python is not installed.
    echo Please install Python 3.7 or higher.
    pause
    exit /b 1
)

REM Ensure required packages are installed
echo Installing/validating build dependencies...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

REM Clean previous builds
echo Cleaning previous build artifacts...
del /f /q projectrock.exe >nul 2>&1
del /f /q projectrock.spec >nul 2>&1
rmdir /s /q dist >nul 2>&1
rmdir /s /q build >nul 2>&1

REM Build the one-file executable
echo Building ProjectRock executable...
python -m PyInstaller --noconfirm --clean --onefile --name projectrock "unified_scanner.py" ^
    --add-data "rockyou-60.txt;." ^
    --add-data "proxies.txt;." ^
    --add-data "sample_passwords.txt;." ^
    --add-data "sample_urls.txt;." ^
    --add-data "manual_urls.txt;."

if errorlevel 1 (
    echo.
    echo Build failed. Check PyInstaller output above.
    pause
    exit /b 1
)

echo.
echo Build succeeded. Executable is located at dist\projectrock.exe
echo You can run it with: dist\projectrock.exe
pause
