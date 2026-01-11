@echo off
chcp 65001 >nul 2>&1
echo ========================================
echo FastAPI Server Startup
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

echo Starting FastAPI server...
echo Server URL: http://localhost:8000
echo.
echo To stop server, press Ctrl+C
echo.

cd /d "%CURRENT_DIR%
%PYTHON_CMD% api_server.py

pause
