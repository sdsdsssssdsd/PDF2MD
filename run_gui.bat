@echo off
cd /d "%~dp0"
REM Prefer the Python that is already on PATH / active venv.
where pythonw >nul 2>nul
if %ERRORLEVEL%==0 (
  start "" pythonw "%~dp0run_gui.py"
  exit /b 0
)
where python >nul 2>nul
if %ERRORLEVEL%==0 (
  python "%~dp0run_gui.py"
  exit /b %ERRORLEVEL%
)
echo Python not found. Activate your venv or install Python 3.10+, then retry.
pause
exit /b 1
