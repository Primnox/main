@echo off
echo ==============================================
echo Launching Primnox...
echo ==============================================

if not exist "backend\venv\Scripts\activate.bat" (
    echo [*] Virtual environment not found. Using global python instead.
    set PY_CMD=python server.py
) else (
    set PY_CMD=call venv\Scripts\activate.bat ^&^& python server.py
)

echo [*] Starting Backend Server...
cd backend
start "Primnox Backend" cmd /k "%PY_CMD%"
cd ..

echo [*] Starting Frontend UI...
cd frontend
start "Primnox UI" cmd /k "npm run electron:dev"
cd ..

echo [+] Services are launching in separate windows.
