@echo off
rem Console menu (ASCII-only launcher; Korean is printed by Python). Web UI: run.bat
setlocal
cd /d "%~dp0"
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PY="
where py  >nul 2>nul && set "PY=py -3"
if not defined PY ( where python >nul 2>nul && set "PY=python" )
if not defined PY ( echo [ERROR] Python not found. & pause & exit /b 1 )
set "AMSRFID_RUNNING_BAT=%~f0"
%PY% -m amsrfid update
%PY% -m amsrfid menu
pause
