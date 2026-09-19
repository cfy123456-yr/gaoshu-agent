@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "APP_DIR=%SCRIPT_DIR%.."
set "PYTHON=%APP_DIR%\tools\python-3.13.13-embed\python.exe"

if exist "%PYTHON%" goto run
set "PYTHON=%APP_DIR%\.venv\Scripts\python.exe"

:run
"%PYTHON%" "%SCRIPT_DIR%verify_deployment.py" %*
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" pause
exit /b %EXIT_CODE%
