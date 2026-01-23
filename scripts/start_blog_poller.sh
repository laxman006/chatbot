#!/bin/bash
# Blog Poller Service Starter for Linux/Unix/Mac
# This script starts the blog polling service as a background daemon

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="$PROJECT_ROOT/logs"
PID_FILE="$PROJECT_ROOT/data/blog_poller.pid"
LOG_FILE="$LOG_DIR/blog_poller.log"

# Create necessary directories
mkdir -p "$LOG_DIR"
mkdir -p "$(dirname "$PID_FILE")"

# Check if already running
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "Blog poller is already running (PID: $PID)"
        echo "To stop it, run: kill $PID"
        exit 1
    else
        # Remove stale PID file
        rm -f "$PID_FILE"
    fi
fi

# Start the service
echo "Starting blog poller service..."
cd "$PROJECT_ROOT"

# Run in background and save PID
nohup python3 "$SCRIPT_DIR/poll_blogs.py" --continuous > "$LOG_FILE" 2>&1 &
PID=$!

# Save PID
echo $PID > "$PID_FILE"

echo "Blog poller started (PID: $PID)"
echo "Log file: $LOG_FILE"
echo "PID file: $PID_FILE"
echo ""
echo "To stop the service, run:"
echo "  kill $PID"
echo "or"
echo "  ./scripts/stop_blog_poller.sh"
