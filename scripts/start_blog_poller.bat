@echo off
REM Blog Poller Service Starter for Windows
REM This script starts the blog polling service as a background process

set SCRIPT_DIR=%~dp0
set PROJECT_ROOT=%SCRIPT_DIR%..
set LOG_DIR=%PROJECT_ROOT%\logs
set PID_FILE=%PROJECT_ROOT%\data\blog_poller.pid
set LOG_FILE=%LOG_DIR%\blog_poller.log

REM Create necessary directories
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
if not exist "%PROJECT_ROOT%\data" mkdir "%PROJECT_ROOT%\data"

REM Check if already running
if exist "%PID_FILE%" (
    for /f "tokens=1" %%i in ('type "%PID_FILE%"') do set PID=%%i
    tasklist /FI "PID eq %PID%" 2>NUL | find /I "%PID%" >NUL
    if %ERRORLEVEL% == 0 (
        echo Blog poller is already running (PID: %PID%)
        echo To stop it, run: taskkill /PID %PID% /F
        exit /b 1
    ) else (
        REM Remove stale PID file
        del "%PID_FILE%"
    )
)

REM Start the service
echo Starting blog poller service...
cd /d "%PROJECT_ROOT%"

REM Start Python process in background
start /B python "%SCRIPT_DIR%poll_blogs.py" --continuous > "%LOG_FILE%" 2>&1

REM Get the PID (Windows doesn't easily capture background process PID)
REM We'll use a workaround - store the process name instead
echo python > "%PID_FILE%"

echo Blog poller started
echo Log file: %LOG_FILE%
echo PID file: %PID_FILE%
echo.
echo To stop the service, find the Python process and kill it:
echo   tasklist ^| findstr python
echo   taskkill /F /IM python.exe
echo.
echo Or use: scripts\stop_blog_poller.bat

pause
