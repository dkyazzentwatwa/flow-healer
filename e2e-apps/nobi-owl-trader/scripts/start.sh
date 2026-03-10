#!/bin/bash

# NobiBot Start Script
# Starts both the Python API and Next.js dashboard

echo "============================================"
echo "       NobiBot - Starting Services"
echo "============================================"
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# Check if .env exists
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}Warning: .env file not found. Copying from .env.example...${NC}"
    cp .env.example .env
    echo "Please edit .env with your API keys if needed."
    echo ""
fi

# Find Python - prefer 3.12, then 3.11, then fallback
PYTHON_CMD=""
if command -v python3.12 &> /dev/null; then
    PYTHON_CMD="python3.12"
elif command -v python3.11 &> /dev/null; then
    PYTHON_CMD="python3.11"
elif [ -d "venv" ]; then
    source venv/bin/activate
    PYTHON_CMD="python"
else
    echo -e "${RED}Error: Python 3.11 or 3.12 not found.${NC}"
    echo "Please install Python 3.12: brew install python@3.12"
    exit 1
fi

echo -e "Using Python: ${GREEN}$PYTHON_CMD${NC}"
$PYTHON_CMD --version
echo ""

# Check if virtual environment exists
if [ -d "venv" ]; then
    echo "Activating virtual environment..."
    source venv/bin/activate
else
    echo -e "${YELLOW}No virtual environment found. Creating one...${NC}"
    $PYTHON_CMD -m venv venv
    source venv/bin/activate
    echo "Installing dependencies..."
    pip install -r requirements.txt
fi

# Start Python API in background
echo ""
echo -e "${GREEN}Starting Python API on http://localhost:8000...${NC}"
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 &
API_PID=$!

# Wait a moment for API to start
sleep 3

# Check if API is running
if kill -0 $API_PID 2>/dev/null; then
    echo -e "${GREEN}API started successfully (PID: $API_PID)${NC}"
else
    echo -e "${RED}Failed to start API. Check logs above for errors.${NC}"
    exit 1
fi

# Start Next.js dashboard
echo ""
echo -e "${GREEN}Starting Dashboard on http://localhost:3000...${NC}"
cd "$PROJECT_DIR/dashboard"

# Check if node_modules exists
if [ ! -d "node_modules" ]; then
    echo "Installing dashboard dependencies..."
    npm install
fi

npm run dev &
DASHBOARD_PID=$!

echo ""
echo "============================================"
echo -e "${GREEN}Services started!${NC}"
echo ""
echo "  API:        http://localhost:8000"
echo "  API Docs:   http://localhost:8000/docs"
echo "  Dashboard:  http://localhost:3000"
echo ""
echo "Press Ctrl+C to stop all services"
echo "============================================"

# Handle shutdown
cleanup() {
    echo ""
    echo "Shutting down services..."
    kill $API_PID 2>/dev/null
    kill $DASHBOARD_PID 2>/dev/null
    exit 0
}

trap cleanup SIGINT SIGTERM

# Wait for processes
wait
