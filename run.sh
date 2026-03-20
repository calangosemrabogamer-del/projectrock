#!/bin/bash

# WordPress Scanner Launcher Script

echo "======================================"
echo "WordPress Username Detector & Scanner"
echo "======================================"
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed"
    echo "Please install Python 3.7 or higher"
    exit 1
fi

# Check Python version
PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
echo "Python version: $PYTHON_VERSION"

# Navigate to script directory
cd "$(dirname "$0")"

# Check if dependencies are installed
echo "Checking dependencies..."
if ! python3 -c "import requests, bs4, urllib3" 2>/dev/null; then
    echo ""
    echo "Installing required dependencies..."
    pip install -r requirements.txt
    
    if [ $? -ne 0 ]; then
        echo ""
        echo "Error: Failed to install dependencies"
        echo "Please run manually: pip install -r requirements.txt"
        exit 1
    fi
fi

echo ""
echo "All dependencies are installed!"
echo "Launching WordPress Scanner..."
echo ""

# Launch the application
python3 unified_scanner.py

# Check exit status
if [ $? -ne 0 ]; then
    echo ""
    echo "Application exited with an error"
    echo "Check logs for details"
    exit 1
fi
