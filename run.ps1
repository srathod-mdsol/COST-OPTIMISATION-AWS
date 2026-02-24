# AWS Cost Optimization Tool - Run Script (PowerShell)
# Usage: .\run.ps1 [command]
# Commands: setup, dashboard, etl, migrate, test, help

param(
    [Parameter(Position=0)]
    [string]$Command = "help"
)

$ErrorActionPreference = "Stop"

# Get the directory where this script is located
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

# Set PYTHONPATH to include project root
$env:PYTHONPATH = "$ScriptDir;$env:PYTHONPATH"

# Virtual environment paths
$VenvPath = Join-Path $ScriptDir "venv"
$Python = Join-Path $VenvPath "Scripts\python.exe"
$Pip = Join-Path $VenvPath "Scripts\pip.exe"

# Colors for output
function Write-Success { Write-Host $args -ForegroundColor Green }
function Write-Error { Write-Host $args -ForegroundColor Red }
function Write-Info { Write-Host $args -ForegroundColor Cyan }
function Write-Warning { Write-Host $args -ForegroundColor Yellow }

# Check if virtual environment exists
function Check-Venv {
    if (-not (Test-Path $VenvPath)) {
        Write-Error "Virtual environment not found!"
        Write-Info "Run '.\run.ps1 setup' first to create the environment."
        exit 1
    }
}

# Check if .env file exists
function Check-Env {
    $envFile = Join-Path $ScriptDir ".env"
    $envExample = Join-Path $ScriptDir ".env.example"
    
    if (-not (Test-Path $envFile)) {
        Write-Warning ".env file not found!"
        if (Test-Path $envExample) {
            Write-Info "Copying .env.example to .env..."
            Copy-Item $envExample $envFile
            Write-Warning "Please edit .env file with your AWS credentials before running the application."
        } else {
            Write-Error "Please create a .env file with your AWS credentials."
            exit 1
        }
    }
}

# Setup virtual environment and install dependencies
function Setup {
    Write-Info "Setting up AWS Cost Optimization Tool..."
    
    # Check Python version
    $pythonVersion = python --version 2>&1
    Write-Info "Python version: $pythonVersion"
    
    # Create virtual environment
    if (-not (Test-Path $VenvPath)) {
        Write-Info "Creating virtual environment..."
        python -m venv $VenvPath
        Write-Success "Virtual environment created."
    } else {
        Write-Info "Virtual environment already exists."
    }
    
    # Activate and install dependencies
    Write-Info "Installing dependencies..."
    & $Python -m pip install --upgrade pip
    & $Pip install -r (Join-Path $ScriptDir "requirements.txt")
    
    # Install package in development mode
    & $Pip install -e $ScriptDir
    
    Write-Success "Dependencies installed."
    
    # Check for .env file
    Check-Env
    
    # Create data directory
    $dataDir = Join-Path $ScriptDir "data"
    if (-not (Test-Path $dataDir)) {
        New-Item -ItemType Directory -Path $dataDir | Out-Null
    }
    
    Write-Success "Setup complete!"
    Write-Info ""
    Write-Info "Next steps:"
    Write-Info "1. Edit .env file with your AWS credentials"
    Write-Info "2. Run '.\run.ps1 migrate' to initialize the database"
    Write-Info "3. Run '.\run.ps1 dashboard' to start the application"
}

# Run database migrations
function Migrate {
    Check-Venv
    Check-Env
    
    Write-Info "Running database migrations..."
    
    # Create data directory if it doesn't exist
    $dataDir = Join-Path $ScriptDir "data"
    if (-not (Test-Path $dataDir)) {
        New-Item -ItemType Directory -Path $dataDir | Out-Null
    }
    
    # Run migrations
    $migrateScript = Join-Path $ScriptDir "database\migrations\migrate.py"
    & $Python $migrateScript init
    & $Python $migrateScript seed
    & $Python $migrateScript verify
    
    Write-Success "Database migrations complete!"
}

# Run the Streamlit dashboard
function Dashboard {
    Check-Venv
    Check-Env
    
    Write-Info "Starting Streamlit dashboard..."
    
    # Run Streamlit
    $dashboardPath = Join-Path $ScriptDir "ui\dashboard.py"
    & $Python -m streamlit run $dashboardPath --server.port 8501 --server.address localhost --browser.gatherUsageStats false
}

# Run ETL process
function Etl {
    Check-Venv
    Check-Env
    
    Write-Info "Running ETL process..."
    
    $mainPath = Join-Path $ScriptDir "main.py"
    & $Python $mainPath
    
    Write-Success "ETL process complete!"
}

# Run ETL scheduler
function Scheduler {
    Check-Venv
    Check-Env
    
    Write-Info "Starting ETL scheduler..."
    
    $schedulerPath = Join-Path $ScriptDir "etl\scheduler.py"
    & $Python $schedulerPath
}

# Run tests
function Test {
    Check-Venv
    
    Write-Info "Running tests..."
    
    # Install test dependencies
    & $Pip install pytest pytest-asyncio pytest-cov
    
    # Run tests
    $testsPath = Join-Path $ScriptDir "tests"
    & $Python -m pytest $testsPath -v --cov=. --cov-report=term-missing
    
    Write-Success "Tests complete!"
}

# Clean up generated files
function Clean {
    Write-Info "Cleaning up..."
    
    # Remove Python cache
    Get-ChildItem -Path $ScriptDir -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Get-ChildItem -Path $ScriptDir -Recurse -File -Filter "*.pyc" | Remove-Item -Force -ErrorAction SilentlyContinue
    Get-ChildItem -Path $ScriptDir -Recurse -File -Filter "*.pyo" | Remove-Item -Force -ErrorAction SilentlyContinue
    
    # Remove .pytest_cache
    $pytestCache = Join-Path $ScriptDir ".pytest_cache"
    if (Test-Path $pytestCache) {
        Remove-Item -Path $pytestCache -Recurse -Force -ErrorAction SilentlyContinue
    }
    
    # Remove coverage files
    $coverageFile = Join-Path $ScriptDir ".coverage"
    if (Test-Path $coverageFile) {
        Remove-Item -Path $coverageFile -Force -ErrorAction SilentlyContinue
    }
    
    $htmlcovDir = Join-Path $ScriptDir "htmlcov"
    if (Test-Path $htmlcovDir) {
        Remove-Item -Path $htmlcovDir -Recurse -Force -ErrorAction SilentlyContinue
    }
    
    Write-Success "Cleanup complete!"
}

# Show help
function Help {
    Write-Host ""
    Write-Host "AWS Cost Optimization Tool - Run Script"
    Write-Host ""
    Write-Host "Usage: .\run.ps1 [command]"
    Write-Host ""
    Write-Host "Commands:"
    Write-Host "  setup      Setup virtual environment and install dependencies"
    Write-Host "  migrate    Initialize and seed the database"
    Write-Host "  dashboard  Run the Streamlit dashboard"
    Write-Host "  etl        Run the ETL process once"
    Write-Host "  scheduler  Run the ETL scheduler (continuous)"
    Write-Host "  test       Run the test suite"
    Write-Host "  clean      Remove generated files and caches"
    Write-Host "  help       Show this help message"
    Write-Host ""
    Write-Host "Examples:"
    Write-Host "  .\run.ps1 setup       # First time setup"
    Write-Host "  .\run.ps1 migrate     # Initialize database"
    Write-Host "  .\run.ps1 dashboard   # Start the web application"
    Write-Host ""
}

# Main script
switch ($Command.ToLower()) {
    "setup" { Setup }
    "migrate" { Migrate }
    "dashboard" { Dashboard }
    "etl" { Etl }
    "scheduler" { Scheduler }
    "test" { Test }
    "clean" { Clean }
    "help" { Help }
    default {
        Write-Error "Unknown command: $Command"
        Help
        exit 1
    }
}
