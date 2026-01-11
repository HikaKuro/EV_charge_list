@echo off
chcp 65001 >nul 2>&1
echo ========================================
echo Server Stop Script
echo ========================================
echo.

REM Stop FastAPI server (port 8000)
echo Stopping FastAPI server (port 8000)...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000 ^| findstr LISTENING') do (
    taskkill /F /PID %%a >nul 2>&1
    echo FastAPI server stopped (PID: %%a)
)

REM Stop React dev server (port 5173)
echo Stopping React dev server (port 5173)...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :5173 ^| findstr LISTENING') do (
    taskkill /F /PID %%a >nul 2>&1
    echo React dev server stopped (PID: %%a)
)

echo.
echo All servers have been stopped
echo.
pause
