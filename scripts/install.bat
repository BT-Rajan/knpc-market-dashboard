@echo off
REM KNPC Market Intelligence Dashboard - Windows Installer
REM Prerequisites: Python 3.10+, Node.js 18+, a reachable MySQL DB/user
REM (see backend\schema.sql to create them).

setlocal enabledelayedexpansion
set "VERSION=1.1"
set "PROJECT=KNPC Market Intelligence Dashboard"

cls
echo.
echo ============================================================================
echo                   %PROJECT% - Windows Installer v%VERSION%
echo ============================================================================
echo.

echo Checking for Python 3.10+...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found! Install from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VER=%%i
echo [OK] Python %PYTHON_VER% found

echo Checking for Node.js 18+...
node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Node.js not found! Install 18+ LTS from https://nodejs.org/
    pause
    exit /b 1
)
for /f "tokens=*" %%i in ('node --version 2^>^&1') do set NODE_VER=%%i
echo [OK] Node %NODE_VER% found

echo.
echo ============================================================================
echo Backend setup (FastAPI)
echo ============================================================================
echo.

cd /d "%~dp0\.."
cd backend

if not exist venv (
    echo Creating Python virtual environment...
    python -m venv venv
    if !errorlevel! neq 0 ( echo [ERROR] Failed to create virtual environment & pause & exit /b 1 )
)
call venv\Scripts\activate.bat

python -m pip install --upgrade pip >nul 2>&1
echo Installing Python dependencies...
pip install -q -r requirements.txt
if !errorlevel! neq 0 ( echo [ERROR] Failed to install Python dependencies & pause & exit /b 1 )
echo [OK] Python dependencies installed

if not exist .env (
    echo.
    echo ---- Database and admin account setup ----
    set /p DB_HOST="MySQL host [localhost]: "
    if "!DB_HOST!"=="" set "DB_HOST=localhost"
    set /p DB_PORT="MySQL port [3306]: "
    if "!DB_PORT!"=="" set "DB_PORT=3306"
    set /p DB_NAME="Database name [knpc_dashboard]: "
    if "!DB_NAME!"=="" set "DB_NAME=knpc_dashboard"
    set /p DB_USER="MySQL user: "
    set /p DB_PASSWORD="MySQL password: "
    set /p ADMIN_PASSWORD="Password for the 'admin' account: "
    set /p USER_PASSWORD="Password for the 'user' (viewer) account: "

    for /f "delims=" %%h in ('python -c "import secrets; print(secrets.token_urlsafe(48))"') do set SESSION_SECRET=%%h
    for /f "delims=" %%h in ('python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"') do set ENCRYPTION_KEY=%%h
    for /f "delims=" %%h in ('python -c "import bcrypt; print(bcrypt.hashpw('!ADMIN_PASSWORD!'.encode(), bcrypt.gensalt()).decode())"') do set ADMIN_PASSWORD_HASH=%%h
    for /f "delims=" %%h in ('python -c "import bcrypt; print(bcrypt.hashpw('!USER_PASSWORD!'.encode(), bcrypt.gensalt()).decode())"') do set USER_PASSWORD_HASH=%%h

    (
        echo DB_HOST=!DB_HOST!
        echo DB_PORT=!DB_PORT!
        echo DB_NAME=!DB_NAME!
        echo DB_USER=!DB_USER!
        echo DB_PASSWORD=!DB_PASSWORD!
        echo SESSION_SECRET=!SESSION_SECRET!
        echo ENCRYPTION_KEY=!ENCRYPTION_KEY!
        echo ADMIN_PASSWORD_HASH=!ADMIN_PASSWORD_HASH!
        echo USER_PASSWORD_HASH=!USER_PASSWORD_HASH!
        echo ALLOWED_ORIGINS=http://localhost:5173
        echo SCRAPE_FREQUENCY_MINUTES=30
        echo DEEPSEEK_API_KEY=
        echo CLAUDE_API_KEY=
    ) > .env
    set "ADMIN_PASSWORD="
    set "USER_PASSWORD="
    set "DB_PASSWORD="
    echo [OK] backend\.env written
) else (
    echo [OK] backend\.env already exists, leaving it as-is
)

echo Verifying the app imports with this config...
python -c "from app.main import app; print('[OK] FastAPI app imports successfully')"
if !errorlevel! neq 0 ( echo [ERROR] App failed to import -- check backend\.env & pause & exit /b 1 )

call venv\Scripts\deactivate.bat
cd ..

echo.
echo ============================================================================
echo Frontend setup (React + Vite)
echo ============================================================================
echo.

cd frontend
echo Installing Node.js dependencies (this can take a few minutes)...
call npm install --legacy-peer-deps
if !errorlevel! neq 0 ( echo [ERROR] npm install failed & pause & exit /b 1 )

echo Building React frontend...
call npm run build
if !errorlevel! neq 0 ( echo [ERROR] Frontend build failed & pause & exit /b 1 )
echo [OK] Frontend built successfully
cd ..

echo.
echo ============================================================================
echo Installation Complete!
echo ============================================================================
echo.
echo Gmail sending is NOT set here -- log in as admin and set it under
echo Admin -^> Email -^> Gmail Settings (uses an App Password, not your
echo account password).
echo.
echo Start Backend:
echo   cd backend ^&^& venv\Scripts\activate.bat ^&^& python run.py
echo   (backend serves on http://localhost:8000, including the built frontend)
echo.
echo Start Frontend dev server instead (hot reload, optional):
echo   cd frontend ^&^& npm run dev   (http://localhost:5173)
echo.
echo Docs: README.md (root)
echo.
pause >nul
exit /b 0
