@echo off
setlocal DisableDelayedExpansion
cd /d "%~dp0"
title Hyperpass Research Web

if exist "%~dp0Hyperpass-Research-Web.exe" (
    "%~dp0Hyperpass-Research-Web.exe"
    goto :finished
)

py -3 -c "import sys; sys.exit(sys.version_info < (3, 11))" >nul 2>&1
if not errorlevel 1 (
    py -3 "%~dp0app.py"
    goto :finished
)

for /f "delims=" %%P in ('where python.exe 2^>nul') do call :try_python "%%P"
if defined PYTHON_FOUND goto :finished

echo.
echo Python 3.11 or newer is required for this source package.
echo Install Python from https://www.python.org/downloads/
echo Select "Add python.exe to PATH", then open this file again.
echo No pip, npm, Codex, or broker API setup is required.
echo.
pause
exit /b 1

:try_python
if defined PYTHON_FOUND exit /b
if /I "%~1"=="%LOCALAPPDATA%\Microsoft\WindowsApps\python.exe" exit /b
"%~1" -c "import sys; sys.exit(sys.version_info < (3, 11))" >nul 2>&1
if errorlevel 1 exit /b
set "PYTHON_FOUND=1"
"%~1" "%~dp0app.py"
exit /b

:finished
echo.
echo Hyperpass Research Web stopped. You can close this window.
pause
