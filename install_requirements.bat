@echo off
chcp 65001 >nul 2>&1
echo ========================================
echo Installing Python Requirements
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

echo Using Python: %PYTHON_CMD%
echo.

REM Upgrade pip first
echo Upgrading pip...
%PYTHON_CMD% -m pip install --upgrade pip

echo.
echo Installing requirements from requirements.txt...
%PYTHON_CMD% -m pip install -r requirements.txt

echo.
echo ========================================
echo Installation complete!
echo ========================================
echo.
echo If you see any errors above, please check:
echo 1. Python is correctly installed
echo 2. pip is working correctly
echo 3. You have internet connection
echo.
pause
