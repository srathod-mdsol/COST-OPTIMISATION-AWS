@echo off
REM AWS Cost Optimization Tool - Run Script (Windows Batch)
REM Usage: run.bat [command]
REM Commands: setup, dashboard, etl, migrate, test, help

setlocal enabledelayedexpansion

REM Get the directory where this script is located
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

REM Set PYTHONPATH to include project root
set "PYTHONPATH=%SCRIPT_DIR%;%PYTHONPATH%"

REM Virtual environment paths
set "VENV_PATH=%SCRIPT_DIR%venv"
set "PYTHON=%VENV_PATH%\Scripts\python.exe"
set "PIP=%VENV_PATH%\Scripts\pip.exe"

REM Command argument
set "COMMAND=%~1"
if "%COMMAND%"=="" set "COMMAND=help"

REM Main script logic
call :%COMMAND% 2>nul
if errorlevel 1 (
    echo Unknown command: %COMMAND%
    call :help
    exit /b 1
)
exit /b 0

REM ============================================
REM Functions
REM ============================================

:setup
echo.
echo [INFO] Setting up AWS Cost Optimization Tool...
echo.

REM Check Python version
for /f "tokens=*" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo [INFO] Python version: %PYTHON_VERSION%

REM Create virtual environment
if not exist "%VENV_PATH%" (
    echo [INFO] Creating virtual environment...
    python -m venv "%VENV_PATH%"
    echo [OK] Virtual environment created.
) else (
    echo [INFO] Virtual environment already exists.
)

REM Install dependencies
echo [INFO] Installing dependencies...
"%PYTHON%" -m pip install --upgrade pip >nul 2>&1
"%PIP%" install -r "%SCRIPT_DIR%requirements.txt" >nul 2>&1

REM Install package in development mode
"%PIP%" install -e "%SCRIPT_DIR%" >nul 2>&1

echo [OK] Dependencies installed.

REM Check for .env file
if not exist "%SCRIPT_DIR%.env" (
    echo [WARN] .env file not found!
    if exist "%SCRIPT_DIR%.env.example" (
        echo [INFO] Copying .env.example to .env...
        copy "%SCRIPT_DIR%.env.example" "%SCRIPT_DIR%.env" >nul
        echo [WARN] Please edit .env file with your AWS credentials before running the application.
    ) else (
        echo [ERROR] Please create a .env file with your AWS credentials.
        exit /b 1
    )
)

REM Create data directory
if not exist "%SCRIPT_DIR%data" mkdir "%SCRIPT_DIR%data"

echo.
echo [OK] Setup complete!
echo.
echo [INFO] Next steps:
echo [INFO] 1. Edit .env file with your AWS credentials
echo [INFO] 2. Run 'run.bat migrate' to initialize the database
echo [INFO] 3. Run 'run.bat dashboard' to start the application
echo.
exit /b 0

:migrate
call :check_venv
call :check_env

echo.
echo [INFO] Running database migrations...

REM Create data directory if it doesn't exist
if not exist "%SCRIPT_DIR%data" mkdir "%SCRIPT_DIR%data"

REM Run migrations
"%PYTHON%" "%SCRIPT_DIR%database\migrations\migrate.py" init
"%PYTHON%" "%SCRIPT_DIR%database\migrations\migrate.py" seed
"%PYTHON%" "%SCRIPT_DIR%database\migrations\migrate.py" verify

echo.
echo [OK] Database migrations complete!
echo.
exit /b 0

:dashboard
call :check_venv
call :check_env

echo.
echo [INFO] Starting Streamlit dashboard...
echo.

REM Run Streamlit
"%PYTHON%" -m streamlit run "%SCRIPT_DIR%ui\dashboard.py" --server.port 8501 --server.address localhost --browser.gatherUsageStats false
exit /b 0

:etl
call :check_venv
call :check_env

echo.
echo [INFO] Running ETL process...

"%PYTHON%" "%SCRIPT_DIR%main.py"

echo.
echo [OK] ETL process complete!
echo.
exit /b 0

:scheduler
call :check_venv
call :check_env

echo.
echo [INFO] Starting ETL scheduler...
echo.

"%PYTHON%" "%SCRIPT_DIR%etl\scheduler.py"
exit /b 0

:test
call :check_venv

echo.
echo [INFO] Running tests...

REM Install test dependencies
"%PIP%" install pytest pytest-asyncio pytest-cov >nul 2>&1

REM Run tests
"%PYTHON%" -m pytest "%SCRIPT_DIR%tests" -v --cov=. --cov-report=term-missing

echo.
echo [OK] Tests complete!
echo.
exit /b 0

:clean
echo.
echo [INFO] Cleaning up...

REM Remove Python cache
for /d /r "%SCRIPT_DIR%" %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d" 2>nul
del /s /q "%SCRIPT_DIR%*.pyc" 2>nul
del /s /q "%SCRIPT_DIR%*.pyo" 2>nul

REM Remove .pytest_cache
if exist "%SCRIPT_DIR%.pytest_cache" rd /s /q "%SCRIPT_DIR%.pytest_cache" 2>nul

REM Remove coverage files
if exist "%SCRIPT_DIR%.coverage" del "%SCRIPT_DIR%.coverage" 2>nul
if exist "%SCRIPT_DIR%htmlcov" rd /s /q "%SCRIPT_DIR%htmlcov" 2>nul

echo.
echo [OK] Cleanup complete!
echo.
exit /b 0

:help
echo.
echo AWS Cost Optimization Tool - Run Script
echo.
echo Usage: run.bat [command]
echo.
echo Commands:
echo   setup      Setup virtual environment and install dependencies
echo   migrate    Initialize and seed the database
echo   dashboard  Run the Streamlit dashboard
echo   etl        Run the ETL process once
echo   scheduler  Run the ETL scheduler (continuous)
echo   test       Run the test suite
echo   clean      Remove generated files and caches
echo   help       Show this help message
echo.
echo Examples:
echo   run.bat setup       # First time setup
echo   run.bat migrate     # Initialize database
echo   run.bat dashboard   # Start the web application
echo.
exit /b 0

REM ============================================
REM Helper Functions
REM ============================================

:check_venv
if not exist "%VENV_PATH%" (
    echo [ERROR] Virtual environment not found!
    echo [INFO] Run 'run.bat setup' first to create the environment.
    exit /b 1
)
exit /b 0

:check_env
if not exist "%SCRIPT_DIR%.env" (
    echo [WARN] .env file not found!
    if exist "%SCRIPT_DIR%.env.example" (
        echo [INFO] Copying .env.example to .env...
        copy "%SCRIPT_DIR%.env.example" "%SCRIPT_DIR%.env" >nul
        echo [WARN] Please edit .env file with your AWS credentials before running the application.
    ) else (
        echo [ERROR] Please create a .env file with your AWS credentials.
        exit /b 1
    )
)
exit /b 0

endlocal