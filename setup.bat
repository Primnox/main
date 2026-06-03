@echo off
echo ==============================================
echo Primnox Auto-Setup Script
echo ==============================================
echo.

echo [*] Checking Python installation...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Python is not installed or not in PATH! Please install Python 3.10+
    pause
    exit /b
)

echo [*] Checking Node.js installation...
node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Node.js is not installed or not in PATH! Please install Node.js 18+
    pause
    exit /b
)

echo.
echo [*] Setting up Backend Environment...
cd backend
echo [*] Creating virtual environment...
python -m venv venv
call venv\Scripts\activate.bat
echo [*] Installing python dependencies...
pip install --upgrade pip
pip install -r requirements.txt
cd ..

echo.
echo [*] Setting up Frontend Environment...
cd frontend
echo [*] Installing Node modules...
call npm install
cd ..

echo.
echo ==============================================
echo [+] Setup Complete!
echo ==============================================
echo You can now use start.bat to launch Primnox.
pause
