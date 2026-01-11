@echo off
chcp 65001 >nul 2>&1
echo ========================================
echo FastAPI Server Connection Test
echo ========================================
echo.

echo Testing connection to http://localhost:8000...
echo.

REM Try to connect using curl if available
where curl >nul 2>&1
if %errorlevel% equ 0 (
    echo Using curl...
    curl -s http://localhost:8000/health
    if %errorlevel% equ 0 (
        echo.
        echo.
        echo SUCCESS: FastAPI server is running!
    ) else (
        echo.
        echo.
        echo ERROR: Cannot connect to FastAPI server
        echo Please make sure the server is running
    )
) else (
    REM Try using PowerShell
    echo Using PowerShell...
    powershell -Command "try { $response = Invoke-WebRequest -Uri 'http://localhost:8000/health' -UseBasicParsing -TimeoutSec 3; Write-Host $response.Content; Write-Host ''; Write-Host 'SUCCESS: FastAPI server is running!' } catch { Write-Host 'ERROR: Cannot connect to FastAPI server'; Write-Host 'Please make sure the server is running' }"
)

echo.
echo ========================================
pause
