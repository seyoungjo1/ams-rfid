@echo off
rem ams-rfid one-touch launcher. Opens the local web UI in your browser.
rem ASCII-only on purpose: Korean text in a .bat breaks cmd.exe on Korean Windows
rem (cmd reads the file in the OEM codepage before chcp takes effect). All Korean
rem messages are printed by Python instead, where UTF-8 is handled correctly.
setlocal
cd /d "%~dp0"
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

rem --- self-heal: if launched as run_vXXX.bat (dropped by the updater), restore run.bat ---
echo %~nx0 | findstr /I "_v" >nul
if not errorlevel 1 (
  copy /y "%~f0" "%~dp0run.bat" >nul
  start "" "%~dp0run.bat"
  exit /b 0
)

rem --- find Python (py launcher first) ---
set "PY="
where py  >nul 2>nul && set "PY=py -3"
if not defined PY ( where python >nul 2>nul && set "PY=python" )
if not defined PY (
  echo [ERROR] Python not found. Install Python 3.11+ from https://www.python.org
  pause
  exit /b 1
)

rem --- tell the updater which .bat is currently running (it cannot overwrite itself) ---
set "AMSRFID_RUNNING_BAT=%~f0"

rem --- dependencies for port detection and portable client extraction ---
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)"
if errorlevel 1 (
  echo [ERROR] Python 3.11 or later is required.
  pause
  exit /b 1
)
%PY% -c "import serial.tools.list_ports, py7zr" >nul 2>nul
if errorlevel 1 (
  echo Preparing Python dependencies. This runs once and may take a minute...
  %PY% -m pip install -r "%~dp0requirements.txt"
  if errorlevel 1 (
    echo [ERROR] Dependency installation failed. Check the messages above.
    pause
    exit /b 1
  )
)

rem --- auto-update when token.txt is present. Use the standalone module path so a broken
rem     package file (e.g. a corrupted pm3.py) can still self-heal via re-download. ---
%PY% -m amsrfid.update

rem --- launch the local web UI ONLY. No driver install, no flashing, no drive scan at startup.
rem     Anything that touches the system (driver/firmware) is a manual button inside the UI. ---
if "%~1"=="" (
  %PY% -m amsrfid ui
) else (
  %PY% -m amsrfid %*
)

echo.
pause
