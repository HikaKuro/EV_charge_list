@echo off
chcp 65001 >nul 2>&1
echo ========================================
echo EV Charger Dashboard Server Startup
echo ========================================
echo.

REM Get current directory
set "CURRENT_DIR=%~dp0"
if "%CURRENT_DIR:~-1%"=="\" set "CURRENT_DIR=%CURRENT_DIR:~0,-1%"

REM Check if Python is available
where py >nul 2>&1
if %errorlevel% equ 0 (
    set "PYTHON_CMD=py"
) else (
    where python >nul 2>&1
    if %errorlevel% equ 0 (
        set "PYTHON_CMD=python"
    ) else (
        echo ERROR: Python is not found in PATH
        echo Please install Python or add it to PATH
        pause
        exit /b 1
    )
)

REM Start FastAPI server in new window
echo Starting FastAPI server...
start "FastAPI Server" cmd /k "cd /d "%CURRENT_DIR%" && %PYTHON_CMD% api_server.py"

REM Wait for FastAPI server to start (longer wait time)
echo Waiting for FastAPI server to start...
timeout /t 5 /nobreak >nul

REM Check if server is running
echo Checking if FastAPI server is running...
timeout /t 2 /nobreak >nul

REM Start React dev server in new window
echo Starting React dev server...
if not exist "%CURRENT_DIR%\ev-charger-dashboard\package.json" (
    echo ERROR: ev-charger-dashboard directory not found
    pause
    exit /b 1
)
start "React Dev Server" cmd /k "cd /d "%CURRENT_DIR%\ev-charger-dashboard" && npm run dev"

echo.
echo ========================================
echo Both servers have been started
echo ========================================
echo.
echo FastAPI Server: http://localhost:8000
echo React Dashboard: http://localhost:5173
echo.
echo To stop servers, press Ctrl+C in each window
echo.
pause
