@echo off
REM KNPC Dashboard - Windows Installer
REM Comprehensive setup script for Windows 10/11
REM Prerequisites: Python 3.10+, Node.js 18+, a reachable MySQL Server
REM (local or remote) with a user/password that can create databases.

setlocal enabledelayedexpansion
set "VERSION=2.0"
set "PROJECT=KNPC Dashboard"
set "ROOT_DIR=%~dp0"

cls
echo.
echo ============================================================================
echo                   %PROJECT% - Windows Installer v%VERSION%
echo ============================================================================
echo.

REM ---------------------------------------------------------------------
REM Prerequisite checks
REM ---------------------------------------------------------------------
echo Checking for Python 3.10+...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found!
    echo Please install Python 3.10+ from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation
    pause
    exit /b 1
)
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VER=%%i
echo [OK] Python %PYTHON_VER% found

echo Checking for Node.js 18+...
node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Node.js not found!
    echo Please install Node.js 18+ LTS from https://nodejs.org/
    echo Make sure Node is added to PATH
    pause
    exit /b 1
)
for /f "tokens=*" %%i in ('node --version 2^>^&1') do set NODE_VER=%%i
echo [OK] Node %NODE_VER% found

for /f "tokens=*" %%i in ('npm --version 2^>^&1') do set NPM_VER=%%i
echo [OK] npm %NPM_VER% found

REM ---------------------------------------------------------------------
REM Collect DB / credentials up front (only if backend\.env is missing).
REM No external mysql.exe is required -- the database itself is created
REM later via pymysql, which requirements.txt already installs.
REM ---------------------------------------------------------------------
set "ENV_FILE=%ROOT_DIR%backend\.env"
set "NEED_ENV_BOOTSTRAP=0"

if exist "%ENV_FILE%" (
    echo.
    echo [OK] backend\.env already exists - skipping configuration prompts.
    echo      Delete backend\.env and re-run this installer to reconfigure.
) else (
    set "NEED_ENV_BOOTSTRAP=1"
    echo.
    echo ============================================================================
    echo Configuration - this runs once and is saved to backend\.env
    echo ============================================================================
    echo.
    echo Avoid using a double-quote character (") in any value below.
    echo.

    set "DB_HOST_IN=localhost"
    set /p "DB_HOST_IN=MySQL host [localhost]: "
    set "DB_PORT_IN=3306"
    set /p "DB_PORT_IN=MySQL port [3306]: "
    set "DB_NAME_IN=knpc_dashboard"
    set /p "DB_NAME_IN=Database name [knpc_dashboard]: "
    set "DB_USER_IN=root"
    set /p "DB_USER_IN=MySQL user [root]: "
    set "DB_PASSWORD_IN="
    set /p "DB_PASSWORD_IN=MySQL password (blank if none): "

    :ask_admin_pw
    set "ADMIN_PASSWORD_IN="
    set /p "ADMIN_PASSWORD_IN=New password for the 'admin' account (required): "
    if "!ADMIN_PASSWORD_IN!"=="" (
        echo This value is required.
        goto ask_admin_pw
    )

    :ask_user_pw
    set "USER_PASSWORD_IN="
    set /p "USER_PASSWORD_IN=New password for the 'user' (viewer) account (required): "
    if "!USER_PASSWORD_IN!"=="" (
        echo This value is required.
        goto ask_user_pw
    )

    set "DEEPSEEK_KEY_IN="
    set /p "DEEPSEEK_KEY_IN=DeepSeek API key (optional, press Enter to skip): "
    set "CLAUDE_KEY_IN="
    set /p "CLAUDE_KEY_IN=Claude API key (optional, press Enter to skip): "
)

echo.
echo ============================================================================
echo Setting up Backend (FastAPI)
echo ============================================================================
echo.

cd /d "%ROOT_DIR%backend"

REM Create virtual environment
if not exist venv (
    echo Creating Python virtual environment...
    python -m venv venv
    if !errorlevel! neq 0 (
        echo [ERROR] Failed to create virtual environment
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created
) else (
    echo [OK] Virtual environment already exists
)

REM Activate virtual environment
echo Activating virtual environment...
call venv\Scripts\activate.bat
if !errorlevel! neq 0 (
    echo [ERROR] Failed to activate virtual environment
    pause
    exit /b 1
)
echo [OK] Virtual environment activated

REM Upgrade pip
echo Upgrading pip...
python -m pip install --upgrade pip >nul
if !errorlevel! neq 0 (
    echo [WARNING] pip self-upgrade failed, continuing with existing pip
)

REM Install dependencies (errors are shown, not swallowed -- a broken
REM install here breaks everything downstream)
echo Installing Python dependencies...
pip install -r requirements.txt
if !errorlevel! neq 0 (
    echo [ERROR] Failed to install Python dependencies -- see the output above
    pause
    exit /b 1
)
echo [OK] Python dependencies installed

REM Write backend\.env now that bcrypt/cryptography/pymysql are installed
if "%NEED_ENV_BOOTSTRAP%"=="1" (
    echo.
    echo Generating backend\.env and creating the database...
    set "DB_HOST=%DB_HOST_IN%"
    set "DB_PORT=%DB_PORT_IN%"
    set "DB_NAME=%DB_NAME_IN%"
    set "DB_USER=%DB_USER_IN%"
    set "DB_PASSWORD=%DB_PASSWORD_IN%"
    set "ADMIN_PASSWORD=%ADMIN_PASSWORD_IN%"
    set "USER_PASSWORD=%USER_PASSWORD_IN%"
    set "DEEPSEEK_API_KEY=%DEEPSEEK_KEY_IN%"
    set "CLAUDE_API_KEY=%CLAUDE_KEY_IN%"
    python tools\bootstrap_env.py
    if !errorlevel! neq 0 (
        echo [ERROR] Failed to generate backend\.env -- see the output above
        pause
        exit /b 1
    )
    REM Clear plaintext secrets from this shell session
    set "DB_PASSWORD="
    set "ADMIN_PASSWORD="
    set "USER_PASSWORD="
)

REM Verify imports (also confirms .env is valid and DB is reachable enough
REM to build the SQLAlchemy engine)
echo Verifying Python imports...
python -c "from app.main import app; print('[OK] FastAPI app imports successfully')"
if !errorlevel! neq 0 (
    echo [ERROR] Failed to import FastAPI app -- see the output above
    pause
    exit /b 1
)

cd /d "%ROOT_DIR%"

echo.
echo ============================================================================
echo Setting up Frontend (React + Vite)
echo ============================================================================
echo.

cd /d "%ROOT_DIR%frontend"

echo Installing Node.js dependencies...
echo This may take a few minutes...
call npm install --legacy-peer-deps
if !errorlevel! neq 0 (
    echo [ERROR] npm install failed -- see the output above
    pause
    exit /b 1
)
echo [OK] Node.js dependencies installed

echo Building React frontend...
call npm run build
if !errorlevel! neq 0 (
    echo [ERROR] Frontend build failed -- see the output above
    pause
    exit /b 1
)
echo [OK] Frontend built successfully

cd /d "%ROOT_DIR%"

echo.
echo ============================================================================
echo Installation Complete!
echo ============================================================================
echo.
echo Tables and seed data are created automatically the first time the
echo backend starts.
echo.
echo Start Backend:
echo   1. Open PowerShell
echo   2. Run: cd backend
echo   3. Run: .\venv\Scripts\Activate.ps1
echo   4. Run: python run.py
echo   5. Backend will start on http://localhost:8000
echo.
echo Start Frontend (in new PowerShell window, dev mode):
echo   1. Open PowerShell
echo   2. Run: cd frontend
echo   3. Run: npm run dev
echo   4. Frontend will open on http://localhost:5173
echo.
echo Or simply run these commands in sequence:
echo   cd backend ^&^& .\venv\Scripts\Activate.ps1 ^&^& python run.py
echo.
echo Documentation:
echo   - README.md           (Overview)
echo   - FEATURE_UPDATES.md  (Technical details)
echo.
echo Press any key to exit...
pause >nul
exit /b 0
