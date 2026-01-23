#!/bin/bash
# Stop Blog Poller Service for Linux/Unix/Mac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PID_FILE="$PROJECT_ROOT/data/blog_poller.pid"

if [ ! -f "$PID_FILE" ]; then
    echo "Blog poller is not running (PID file not found)"
    exit 1
fi

PID=$(cat "$PID_FILE")

if ps -p "$PID" > /dev/null 2>&1; then
    echo "Stopping blog poller (PID: $PID)..."
    kill "$PID"
    
    # Wait for process to stop
    for i in {1..10}; do
        if ! ps -p "$PID" > /dev/null 2>&1; then
            echo "Blog poller stopped successfully"
            rm -f "$PID_FILE"
            exit 0
        fi
        sleep 1
    done
    
    # Force kill if still running
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "Force killing blog poller..."
        kill -9 "$PID"
        rm -f "$PID_FILE"
        echo "Blog poller force stopped"
    fi
else
    echo "Blog poller is not running (process not found)"
    rm -f "$PID_FILE"
fi
