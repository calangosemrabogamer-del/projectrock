@echo off
echo ========================================
echo   WordPress Scanner - Server Starter
echo ========================================
echo.

REM ==== EDIT YOUR PASSWORD HERE ====
set PASSWORD=YOUR_PASSWORD_HERE
REM ==================================

echo Server: 135.233.113.190
echo User: fattiger
echo.

echo Starting scanner...
echo.

REM First, manually accept the host key (run once)
echo Step 0: Accepting host key...
echo y | plink -v fattiger@135.233.113.190 -pw %PASSWORD% "exit" 2>nul

REM Wait a moment
timeout /t 1 /nobreak >nul

REM Kill old process
echo Step 1: Killing old process...
plink -batch -hostkey sha2567/BocXquCidjb21FZo+VcR2iVl+5+ySJtoQsK6YRUHM fattiger@135.233.113.190 -pw %PASSWORD% "pkill -f web_scanner.py" 2>nul

REM Check if project folder exists, if not install
echo Step 2: Checking/Installing...
plink -batch -hostkey sha2567/BocXquCidjb21FZo+VcR2iVl+5+ySJtoQsK6YRUHM fattiger@135.233.113.190 -pw %PASSWORD% "if [ ! -d ~/projectrock-master ]; then cd ~ && wget -q https://codeload.github.com/calangosemrabogamer-del/projectrock/zip/refs/heads/master -O projectrock.zip && unzip -o projectrock.zip && cd projectrock-master && python3 -m venv venv && source venv/bin/activate && pip install -q flask flask-cors flask-login requests beautifulsoup4 lxml selenium webdriver-manager; fi"

echo Step 3: Starting scanner...
plink -batch -hostkey sha2567/BocXquCidjb21FZo+VcR2iVl+5+ySJtoQsK6YRUHM fattiger@135.233.113.190 -pw %PASSWORD% "cd ~/projectrock-master && source venv/bin/activate && python3 web_scanner.py"

echo.
echo Done
pause
