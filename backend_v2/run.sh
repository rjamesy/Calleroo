#!/bin/bash
# Run the Calleroo v2 backend
# Usage: ./run.sh [port]
# Or set PORT environment variable

# Determine script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check if .env exists
if [ ! -f .env ]; then
    echo "ERROR: .env file not found!"
    echo "Copy .env.example to .env and add your OPENAI_API_KEY"
    exit 1
fi

# Install dependencies if needed
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
else
    source venv/bin/activate
fi

# Allow port override via argument or PORT env var
# Priority: CLI arg > PORT env var > default 8000
if [ -n "$1" ]; then
    PORT="$1"
elif [ -z "$PORT" ]; then
    PORT="8000"
fi

# Run the server
echo "Starting Calleroo Backend v2 on port $PORT..."
uvicorn app.main:app --reload --host 0.0.0.0 --port "$PORT"
