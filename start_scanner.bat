@echo off
echo ========================================
echo   WordPress Scanner - Server Starter
echo ========================================
echo.
echo Server: 135.233.113.190
echo User: fattiger
echo.

echo Step 1: Checking and installing if needed...
ssh -o StrictHostKeyChecking=no fattiger@135.233.113.190 "if [ ! -d ~/projectrock-master ]; then cd ~ && wget -q https://codeload.github.com/calangosemrabogamer-del/projectrock/zip/refs/heads/master -O projectrock.zip && unzip -o projectrock.zip && cd projectrock-master && python3 -m venv venv && source venv/bin/activate && pip install -q flask flask-cors flask-login requests beautifulsoup4 lxml selenium webdriver-manager; fi"

echo.
echo Step 2: Killing old process...
ssh -o StrictHostKeyChecking=no fattiger@135.233.113.190 "pkill -f web_scanner.py 2>/dev/null; sleep 1"

echo.
echo Step 3: Starting scanner...
ssh -o StrictHostKeyChecking=no fattiger@135.233.113.190 "cd ~/projectrock-master && source venv/bin/activate && python3 web_scanner.py"

echo.
echo ========================================
echo Done
echo ========================================
pause
