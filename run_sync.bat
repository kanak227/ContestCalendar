@echo off
set "PROJECT_DIR=%~dp0"
set "PYTHON_BIN=%PROJECT_DIR%.venv\Scripts\python.exe"
set "SCRIPT_PATH=%PROJECT_DIR%main.py"
set "LOG_FILE=%PROJECT_DIR%sync.log"

echo --- Sync Started: %date% %time% --- >> "%LOG_FILE%"

cd /d "%PROJECT_DIR%"

"%PYTHON_BIN%" "%SCRIPT_PATH%" >> "%LOG_FILE%" 2>&1

echo --- Sync Finished: %date% %time% --- >> "%LOG_FILE%"
echo. >> "%LOG_FILE%"
