@echo off
setlocal EnableDelayedExpansion

echo.
echo ================================================
echo   Primnox Local Build Script
echo ================================================
echo.

:: ── Get version from package.json ────────────────
for /f "tokens=2 delims=:, " %%v in ('findstr /i "\"version\"" frontend\package.json') do (
    set RAW=%%v
    set VERSION=!RAW:"=!
    goto :got_version
)
:got_version
echo [*] Building Primnox v%VERSION%
echo.

:: ── Step 1: Backend — PyInstaller ────────────────
echo [1/3] Building Python backend with PyInstaller...
cd backend

:: Fetch PII model if not present
if not exist "models\pii" (
    echo     [*] Downloading PII model...
    python -c "from transformers import AutoTokenizer, AutoModelForTokenClassification; AutoTokenizer.from_pretrained('iiiorg/piiranha-v1-detect-personal-information', cache_dir='models/pii'); AutoModelForTokenClassification.from_pretrained('iiiorg/piiranha-v1-detect-personal-information', cache_dir='models/pii')"
)

:: Run PyInstaller
pyinstaller primnox_backend.spec --noconfirm --clean
if errorlevel 1 (
    echo [!] Backend build FAILED.
    cd ..
    exit /b 1
)
echo     [OK] Backend built → backend\dist\primnox_backend\
cd ..

:: ── Step 2: Frontend — Vite ──────────────────────
echo.
echo [2/3] Building React frontend with Vite...
cd frontend
call npm run build
if errorlevel 1 (
    echo [!] Frontend build FAILED.
    cd ..
    exit /b 1
)
echo     [OK] Frontend built → frontend\dist\
cd ..

:: ── Step 3: Electron — Package installer ─────────
echo.
echo [3/3] Packaging Electron installer (NSIS)...
cd frontend
call npm run electron:build
if errorlevel 1 (
    echo [!] Electron packaging FAILED.
    cd ..
    exit /b 1
)
echo     [OK] Installer built → frontend\dist-electron\
cd ..

:: ── Done ─────────────────────────────────────────
echo.
echo ================================================
echo   BUILD COMPLETE — Primnox v%VERSION%
echo ================================================
echo.

:: Find and display the installer path
for /f "delims=" %%f in ('dir /b /s "frontend\dist-electron\Primnox-Setup-*.exe" 2^>nul') do (
    echo   Installer: %%f
)
echo.
echo   To install: run the .exe above as Administrator
echo ================================================
echo.
