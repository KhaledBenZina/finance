#!/bin/bash
# Script to stop the ORB + VWAP Scanner UI

echo "Stopping Streamlit server on port 8501..."

# Find and kill the process on port 8501
PID=$(lsof -ti:8501)

if [ -z "$PID" ]; then
    echo "No process found running on port 8501"
else
    echo "Found process $PID, killing it..."
    kill $PID
    sleep 1
    
    # Check if it's still running
    if lsof -ti:8501 > /dev/null 2>&1; then
        echo "Process still running, force killing..."
        kill -9 $PID
    fi
    
    echo "Streamlit server stopped"
fi

# Alternative: kill all streamlit processes (more aggressive)
# pkill -f streamlit

