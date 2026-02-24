#!/bin/bash

# AWS Cost Optimization Tool - Run Script (Linux/macOS)
# Usage: ./run.sh [command]
# Commands: setup, dashboard, etl, migrate, test, docker-up, docker-down, docker-logs, help

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Set PYTHONPATH to include project root
export PYTHONPATH="$SCRIPT_DIR:$PYTHONPATH"

# Virtual environment path
VENV_PATH="$SCRIPT_DIR/venv"
PYTHON="$VENV_PATH/bin/python"
PIP="$VENV_PATH/bin/pip"

# Print colored message
print_msg() {
    echo -e "${2}${1}${NC}"
}

print_success() { print_msg "$1" "$GREEN"; }
print_error() { print_msg "$1" "$RED"; }
print_info() { print_msg "$1" "$BLUE"; }
print_warning() { print_msg "$1" "$YELLOW"; }

# Check if virtual environment exists
check_venv() {
    if [ ! -d "$VENV_PATH" ]; then
        print_error "Virtual environment not found!"
        print_info "Run './run.sh setup' first to create the environment."
        exit 1
    fi
}

# Check if .env file exists
check_env() {
    if [ ! -f "$SCRIPT_DIR/.env" ]; then
        print_warning ".env file not found!"
        if [ -f "$SCRIPT_DIR/.env.example" ]; then
            print_info "Copying .env.example to .env..."
            cp "$SCRIPT_DIR/.env.example" "$SCRIPT_DIR/.env"
            print_warning "Please edit .env file with your AWS credentials before running the application."
        else
            print_error "Please create a .env file with your AWS credentials."
            exit 1
        fi
    fi
}

# Setup virtual environment and install dependencies
setup() {
    print_info "Setting up AWS Cost Optimization Tool..."
    
    # Check Python version
    PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
    print_info "Python version: $PYTHON_VERSION"
    
    # Create virtual environment
    if [ ! -d "$VENV_PATH" ]; then
        print_info "Creating virtual environment..."
        python3 -m venv "$VENV_PATH"
        print_success "Virtual environment created."
    else
        print_info "Virtual environment already exists."
    fi
    
    # Activate and install dependencies
    print_info "Installing dependencies..."
    source "$VENV_PATH/bin/activate"
    pip install --upgrade pip
    pip install -r "$SCRIPT_DIR/requirements.txt"
    
    # Install package in development mode
    pip install -e "$SCRIPT_DIR"
    
    print_success "Dependencies installed."
    
    # Check for .env file
    check_env
    
    # Create data directory
    mkdir -p "$SCRIPT_DIR/data"
    
    print_success "Setup complete!"
    print_info ""
    print_info "Next steps:"
    print_info "1. Edit .env file with your AWS credentials"
    print_info "2. Run './run.sh migrate' to initialize the database"
    print_info "3. Run './run.sh dashboard' to start the application"
    print_info ""
    print_info "For Docker deployment:"
    print_info "1. Copy .env.docker to .env"
    print_info "2. Run './run.sh docker-up' to start with PostgreSQL"
}

# Run database migrations
migrate() {
    check_venv
    check_env
    
    print_info "Running database migrations..."
    source "$VENV_PATH/bin/activate"
    
    # Create data directory if it doesn't exist (only for SQLite)
    # Check if DATABASE_URL contains 'sqlite' or is not set (defaults to SQLite)
    if echo "${DATABASE_URL:-sqlite}" | grep -q "sqlite"; then
        mkdir -p "$SCRIPT_DIR/data"
    fi
    
    # Run migrations
    "$PYTHON" "$SCRIPT_DIR/database/migrations/migrate.py" init
    "$PYTHON" "$SCRIPT_DIR/database/migrations/migrate.py" seed
    "$PYTHON" "$SCRIPT_DIR/database/migrations/migrate.py" verify
    
    print_success "Database migrations complete!"
}

# Run the Streamlit dashboard
dashboard() {
    check_venv
    check_env
    
    print_info "Starting Streamlit dashboard..."
    source "$VENV_PATH/bin/activate"
    
    # Run Streamlit
    streamlit run "$SCRIPT_DIR/ui/dashboard.py" \
        --server.port 8501 \
        --server.address localhost \
        --browser.gatherUsageStats false
}

# Run ETL process
etl() {
    check_venv
    check_env
    
    print_info "Running ETL process..."
    source "$VENV_PATH/bin/activate"
    
    "$PYTHON" "$SCRIPT_DIR/main.py"
    print_success "ETL process complete!"
}

# Run ETL scheduler
scheduler() {
    check_venv
    check_env
    
    print_info "Starting ETL scheduler..."
    source "$VENV_PATH/bin/activate"
    
    "$PYTHON" "$SCRIPT_DIR/etl/scheduler.py"
}

# Run tests
test() {
    check_venv
    
    print_info "Running tests..."
    source "$VENV_PATH/bin/activate"
    
    # Install test dependencies
    pip install pytest pytest-asyncio pytest-cov
    
    # Run tests
    python -m pytest "$SCRIPT_DIR/tests/" -v --cov=. --cov-report=term-missing
    
    print_success "Tests complete!"
}

# Clean up generated files
clean() {
    print_info "Cleaning up..."
    
    # Remove Python cache
    find "$SCRIPT_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find "$SCRIPT_DIR" -type f -name "*.pyc" -delete 2>/dev/null || true
    find "$SCRIPT_DIR" -type f -name "*.pyo" -Delete 2>/dev/null || true
    
    # Remove .pytest_cache
    rm -rf "$SCRIPT_DIR/.pytest_cache" 2>/dev/null || true
    
    # Remove coverage files
    rm -f "$SCRIPT_DIR/.coverage" 2>/dev/null || true
    rm -rf "$SCRIPT_DIR/htmlcov" 2>/dev/null || true
    
    print_success "Cleanup complete!"
}

# ==========================================
# Docker Commands
# ==========================================

# Start Docker containers
docker_up() {
    print_info "Starting Docker containers..."
    
    # Check if .env.docker exists, copy to .env if .env doesn't exist
    if [ ! -f "$SCRIPT_DIR/.env" ] && [ -f "$SCRIPT_DIR/.env.docker" ]; then
        print_info "Copying .env.docker to .env..."
        cp "$SCRIPT_DIR/.env.docker" "$SCRIPT_DIR/.env"
    fi
    
    # Build and start containers
    docker-compose up -d
    
    print_success "Docker containers started!"
    print_info ""
    print_info "Services:"
    print_info "  - Streamlit App: http://localhost:8501"
    print_info "  - PostgreSQL:    localhost:5432"
    print_info ""
    print_info "Optional services:"
    print_info "  ./run.sh docker-tunnel   # Start ngrok tunnel"
    print_info "  ./run.sh docker-admin    # Start pgAdmin"
}

# Stop Docker containers
docker_down() {
    print_info "Stopping Docker containers..."
    docker-compose down
    print_success "Docker containers stopped!"
}

# View Docker logs
docker_logs() {
    local service="${1:-}"
    if [ -n "$service" ]; then
        docker-compose logs -f "$service"
    else
        docker-compose logs -f
    fi
}

# Start with ngrok tunnel
docker_tunnel() {
    print_info "Starting Docker containers with ngrok tunnel..."
    docker-compose --profile tunnel up -d
    print_success "Started with ngrok tunnel!"
    print_info "Check ngrok UI at http://localhost:4040 for the public URL"
}

# Start with pgAdmin
docker_admin() {
    print_info "Starting Docker containers with pgAdmin..."
    docker-compose --profile admin up -d
    print_success "Started with pgAdmin!"
    print_info "pgAdmin UI: http://localhost:5050"
    print_info "Login: admin@aws-cost-opt.local / admin123"
}

# Rebuild Docker containers
docker_build() {
    print_info "Building Docker containers..."
    docker-compose build --no-cache
    print_success "Docker containers built!"
}

# Show Docker status
docker_status() {
    print_info "Docker container status:"
    docker-compose ps
}

# Reset Docker (stop, remove volumes, restart)
docker_reset() {
    print_warning "This will remove all Docker containers and volumes!"
    read -p "Are you sure? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        print_info "Resetting Docker environment..."
        docker-compose down -v
        docker-compose up -d
        print_success "Docker environment reset!"
    else
        print_info "Reset cancelled."
    fi
}

# Show help
help() {
    echo ""
    echo "AWS Cost Optimization Tool - Run Script"
    echo ""
    echo "Usage: ./run.sh [command]"
    echo ""
    echo "Local Commands:"
    echo "  setup       Setup virtual environment and install dependencies"
    echo "  migrate     Initialize and seed the database"
    echo "  dashboard   Run the Streamlit dashboard"
    echo "  etl         Run the ETL process once"
    echo "  scheduler   Run the ETL scheduler (continuous)"
    echo "  test        Run the test suite"
    echo "  clean       Remove generated files and caches"
    echo ""
    echo "Docker Commands:"
    echo "  docker-up       Start Docker containers (PostgreSQL + Streamlit)"
    echo "  docker-down     Stop Docker containers"
    echo "  docker-logs     View Docker logs (optional: service name)"
    echo "  docker-tunnel   Start with ngrok tunnel for external access"
    echo "  docker-admin    Start with pgAdmin for database management"
    echo "  docker-build    Rebuild Docker containers"
    echo "  docker-status   Show Docker container status"
    echo "  docker-reset    Reset Docker (remove volumes and restart)"
    echo ""
    echo "Help:"
    echo "  help            Show this help message"
    echo ""
    echo "Examples:"
    echo "  ./run.sh setup          # First time setup"
    echo "  ./run.sh migrate        # Initialize database"
    echo "  ./run.sh dashboard      # Start the web application locally"
    echo "  ./run.sh docker-up      # Start with PostgreSQL in Docker"
    echo "  ./run.sh docker-logs    # View all container logs"
    echo "  ./run.sh docker-logs streamlit-app  # View specific service logs"
    echo ""
}

# Main script
case "${1:-help}" in
    setup)
        setup
        ;;
    migrate)
        migrate
        ;;
    dashboard)
        dashboard
        ;;
    etl)
        etl
        ;;
    scheduler)
        scheduler
        ;;
    test)
        test
        ;;
    clean)
        clean
        ;;
    docker-up)
        docker_up
        ;;
    docker-down)
        docker_down
        ;;
    docker-logs)
        docker_logs "$2"
        ;;
    docker-tunnel)
        docker_tunnel
        ;;
    docker-admin)
        docker_admin
        ;;
    docker-build)
        docker_build
        ;;
    docker-status)
        docker_status
        ;;
    docker-reset)
        docker_reset
        ;;
    help|--help|-h)
        help
        ;;
    *)
        print_error "Unknown command: $1"
        help
        exit 1
        ;;
esac
