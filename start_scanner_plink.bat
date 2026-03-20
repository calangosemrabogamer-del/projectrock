@echo off
echo ========================================
echo   WordPress Scanner - Using PuTTY plink
echo ========================================
echo.

REM ==== EDIT YOUR PASSWORD HERE ====
set PASSWORD=YourPasswordHere
REM ==================================

echo Server: 135.233.113.190
echo User: fattiger
echo.

echo First, make sure plink is installed (part of PuTTY)
echo Download from: https://www.chiark.greenend.org.uk/~sgtatham/putty/latest.html
echo.

echo If plink is not in PATH, place it in the same folder as this file
echo.

echo Starting scanner...
echo.

REM Check if plink exists
where plink >nul 2>nul
if %errorlevel% neq 0 (
    echo ERROR: plink not found!
    echo Please install PuTTY and add plink to PATH, or place plink.exe in this folder
    pause
    exit /b 1
)

REM Kill old process
echo Step 1: Killing old process...
plink -batch fattiger@135.233.113.190 -pw %PASSWORD% "pkill -f web_scanner.py" 2>nul

REM Check if project folder exists, if not install
echo Step 2: Checking/Installing...
plink -batch fattiger@135.233.113.190 -pw %PASSWORD% "if [ ! -d ~/projectrock-master ]; then cd ~ && wget -q https://codeload.github.com/calangosemrabogamer-del/projectrock/zip/refs/heads/master -O projectrock.zip && unzip -o projectrock.zip && cd projectrock-master && python3 -m venv venv && source venv/bin/activate && pip install -q flask flask-cors flask-login requests beautifulsoup4 lxml selenium webdriver-manager; fi"

echo Step 3: Starting scanner...
plink -batch fattiger@135.233.113.190 -pw %PASSWORD% "cd ~/projectrock-master && source venv/bin/activate && python3 web_scanner.py"

echo.
echo Done
pause
