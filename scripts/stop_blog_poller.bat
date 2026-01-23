@echo off
REM Stop Blog Poller Service for Windows

set SCRIPT_DIR=%~dp0
set PROJECT_ROOT=%SCRIPT_DIR%..
set PID_FILE=%PROJECT_ROOT%\data\blog_poller.pid

if not exist "%PID_FILE%" (
    echo Blog poller is not running (PID file not found)
    exit /b 1
)

echo Stopping blog poller...
echo.
echo Finding Python processes running poll_blogs.py...

REM Find and kill Python processes running the poller
for /f "tokens=2" %%i in ('tasklist /FI "IMAGENAME eq python.exe" /FO CSV ^| findstr /I "python"') do (
    wmic process where "ProcessId=%%i" get CommandLine 2>NUL | findstr /I "poll_blogs" >NUL
    if %ERRORLEVEL% == 0 (
        echo Killing process %%i...
        taskkill /PID %%i /F >NUL 2>&1
    )
)

REM Also try to kill by process name pattern
taskkill /F /IM python.exe /FI "WINDOWTITLE eq poll_blogs*" >NUL 2>&1

del "%PID_FILE%" 2>NUL

echo Blog poller stopped
pause
