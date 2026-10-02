@echo off
rem 메뉴로 열기 (읽기/복제/목록/업데이트를 번호로 고름). 원터치는 run.bat.
setlocal
cd /d "%~dp0"
chcp 65001 >nul
set "PY="
where py  >nul 2>nul && set "PY=py -3"
if not defined PY ( where python >nul 2>nul && set "PY=python" )
if not defined PY ( echo 파이썬을 찾지 못했습니다. & pause & exit /b 1 )
set "AMSRFID_RUNNING_BAT=%~f0"
%PY% -m amsrfid update
%PY% -m amsrfid menu
pause >nul
