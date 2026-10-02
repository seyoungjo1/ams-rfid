@echo off
rem ams-rfid 원터치 런처 — 꽂고 더블클릭하면 업데이트 확인 후 읽기(키 복구 + .bin 저장)까지 쭉.
rem (cost-analyzer/bwbridge 의 run.bat 과 같은 결: self-heal + 자동 업데이트)
setlocal enabledelayedexpansion
cd /d "%~dp0"
chcp 65001 >nul

rem --- self-heal: 업데이트가 옆에 떨군 run_vXXX.bat 로 실행되면, 자기를 run.bat 으로 되돌린다 ---
echo %~nx0 | findstr /I "_v" >nul
if not errorlevel 1 (
  copy /y "%~f0" "%~dp0run.bat" >nul
  echo run.bat 을 최신본으로 되돌렸습니다. 새 창에서 다시 시작합니다.
  start "" "%~dp0run.bat"
  exit /b 0
)

rem --- 파이썬 찾기 (py 런처 우선) ---
set "PY="
where py  >nul 2>nul && set "PY=py -3"
if not defined PY ( where python >nul 2>nul && set "PY=python" )
if not defined PY (
  echo 파이썬을 찾지 못했습니다. https://www.python.org 에서 3.11 이상을 설치하세요.
  pause
  exit /b 1
)

rem --- 지금 돌고 있는 .bat 이름을 업데이트 모듈에 알려 준다(자기 자신은 못 덮어쓰므로) ---
set "AMSRFID_RUNNING_BAT=%~f0"

rem --- 토큰이 있으면 최신본으로 자동 갱신 ---
%PY% -m amsrfid update

rem --- 원터치: 장치 대기 → 카드 대기 → 종류 확인 → 키 복구 → .bin 저장 ---
rem   인자 없이 더블클릭하면 auto(원터치). 인자를 주면 그대로 넘긴다(clone/menu/info 등).
if "%~1"=="" (
  %PY% -m amsrfid auto
) else (
  %PY% -m amsrfid %*
)

echo.
echo 끝났습니다. 창을 닫으려면 아무 키나 누르세요.
pause >nul
