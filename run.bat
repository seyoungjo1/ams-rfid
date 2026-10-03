@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

echo "%~nx0" | findstr /I "_v" >nul
if not errorlevel 1 (
  copy /y "%~f0" "%~dp0run.bat" >nul
  start "" "%~dp0run.bat"
  exit /b 0
)

rem Always use the project-private runtime. No py/python/PATH lookup.
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0bootstrap.ps1"
if errorlevel 1 (
  if not defined AMSRFID_NO_PAUSE pause
  exit /b 1
)
set "AMSRFID_PYTHON=%~dp0.runtime\python-3.13.12\python.exe"
set "AMSRFID_RUNNING_BAT=%~f0"
"%AMSRFID_PYTHON%" -X utf8 -m amsrfid.update
if "%~1"=="" (
  "%AMSRFID_PYTHON%" -X utf8 -m amsrfid ui
) else (
  "%AMSRFID_PYTHON%" -X utf8 -m amsrfid %*
)
set "AMSRFID_EXIT=%ERRORLEVEL%"
echo.
if not defined AMSRFID_NO_PAUSE pause
exit /b %AMSRFID_EXIT%
