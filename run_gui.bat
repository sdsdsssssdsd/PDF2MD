@echo off
cd /d "%~dp0"
REM Refresh PDF2MD.lnk beside this folder (custom desktop cover icon).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\ensure_shortcut.ps1" -Root "%~dp0." -TargetBat "%~f0" >nul 2>nul

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
