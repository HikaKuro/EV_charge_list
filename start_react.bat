@echo off
chcp 65001 >nul 2>&1
echo ========================================
echo React Dev Server Startup
echo ========================================
echo.

REM Get current directory
set "CURRENT_DIR=%~dp0"
if "%CURRENT_DIR:~-1%"=="\" set "CURRENT_DIR=%CURRENT_DIR:~0,-1%"

REM Change to React project directory
set "REACT_DIR=%CURRENT_DIR%\ev-charger-dashboard"

if not exist "%REACT_DIR%\package.json" (
    echo ERROR: ev-charger-dashboard directory not found
    echo or package.json does not exist
    pause
    exit /b 1
)

echo Starting React dev server...
echo Dashboard URL: http://localhost:5173
echo.
echo To stop server, press Ctrl+C
echo.

cd /d "%REACT_DIR%"
npm run dev

pause
