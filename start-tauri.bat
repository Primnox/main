@echo off
REM ==============================================================
REM  Launch Primnox with the Tauri shell (instead of Electron).
REM
REM  Mirrors start.bat, but runs `npm run tauri:dev` for the UI.
REM  Both shells drive the same React frontend and the same Python
REM  backend on port 4009, so they are interchangeable in dev.
REM
REM  Extra prerequisite over start.bat:
REM    - Rust toolchain      https://rustup.rs
REM    - WebView2 runtime    preinstalled on Windows 11; on Windows 10
REM                          get it from the Microsoft Evergreen page
REM
REM  The first launch compiles the Rust shell and takes several
REM  minutes. Later launches are incremental and start quickly.
REM ==============================================================

echo ==============================================
echo Launching Primnox (Tauri)...
echo ==============================================

where cargo >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Rust not found in PATH. Install it from https://rustup.rs
    echo     then reopen this terminal and run start-tauri.bat again.
    pause
    exit /b
)

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

echo [*] Starting Frontend UI (Tauri)...
echo     First run compiles Rust — expect a few minutes.
cd frontend
start "Primnox UI (Tauri)" cmd /k "npm run tauri:dev"
cd ..

echo [+] Services are launching in separate windows.
