@echo off
echo ========================================
echo   WordPress Scanner - Server Starter
echo ========================================
echo.

echo This will automatically:
echo 1. Connect to your Azure server
echo 2. Update code from GitHub
echo 3. Start the scanner
echo.

echo Server: 135.233.113.190
echo User: fattiger
echo.

echo Press any key to start...
pause >nul

echo.
echo ========================================
echo Connecting and starting scanner...
echo ========================================
echo.

ssh fattiger@135.233.113.190 "pkill -f web_scanner.py; sleep 1; cd ~/projectrock-master 2>/dev/null || { cd ~ && wget -q https://codeload.github.com/calangosemrabogamer-del/projectrock/zip/refs/heads/master -O projectrock.zip && unzip -o projectrock.zip && cd projectrock-master && python3 -m venv venv && source venv/bin/activate && pip install -q flask flask-cors flask-login requests beautifulsoup4 lxml selenium webdriver-manager; }; cd ~/projectrock-master && source venv/bin/activate && python3 web_scanner.py"

echo.
echo ========================================
echo Connection closed
echo ========================================
pause
