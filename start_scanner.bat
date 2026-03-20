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

echo Step 1: Killing old process...
ssh -o StrictHostKeyChecking=no fattiger@135.233.113.190 "pkill -f web_scanner.py" 

echo.
echo Step 2: Starting scanner (will auto-update if needed)...
ssh -o StrictHostKeyChecking=no fattiger@135.233.113.190 "cd ~/projectrock-master && source venv/bin/activate && python3 web_scanner.py"

echo.
echo ========================================
echo Connection closed
echo ========================================
pause
