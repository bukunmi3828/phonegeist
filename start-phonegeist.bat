@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
    echo Python was not found. Install it from https://python.org
    echo Be sure to select "Add Python to PATH" during installation.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating the local Python environment...
    py -3 -m venv .venv
    if errorlevel 1 goto :failed
)

".venv\Scripts\python.exe" -c "import flask, pynput, qrcode" >nul 2>nul
if errorlevel 1 (
    echo Installing Phonegeist dependencies...
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 goto :failed
)

".venv\Scripts\python.exe" typer.py --choose-folder
if errorlevel 1 goto :failed
exit /b 0

:failed
echo.
echo Phonegeist could not start. Review the error above.
pause
exit /b 1
