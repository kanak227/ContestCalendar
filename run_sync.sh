#!/bin/bash

# --- SETTINGS ---
# Get the absolute path of the directory where this script is located
PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PYTHON_BIN="$PROJECT_DIR/.venv/bin/python3"
SCRIPT_PATH="$PROJECT_DIR/main.py"
LOG_FILE="$PROJECT_DIR/sync.log"

# --- EXECUTION ---
echo "--- Sync Started: $(date) ---" >> "$LOG_FILE"

# Change to project directory (important for local file paths like token.json)
cd "$PROJECT_DIR"

# Run the script and append output to log
"$PYTHON_BIN" "$SCRIPT_PATH" >> "$LOG_FILE" 2>&1

echo "--- Sync Finished: $(date) ---" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"
