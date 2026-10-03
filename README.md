# ams-rfid

Proxmark3 **Easy**로 MIFARE Classic 1K / FM11RF08S 원본 카드를 읽고, 대상 카드에 쓴 뒤 되읽어 확인하는 로컬 도구입니다.

## 0.4.0 — 자동 설치와 Easy 펌웨어 복구

1. 이 저장소 폴더를 통째로 새 폴더에 압축 해제하고 Easy를 데이터 USB 케이블로 연결합니다.
2. `run.bat`을 실행합니다. 공식 Python 런타임과 필요한 모듈을 폴더 내부에 자동 준비합니다.
3. 원본 카드를 올리고 **원터치 시작**을 누릅니다.
4. 처음 한 번 Easy용 클라이언트와 DLL을 자동 다운로드·검증·압축 해제합니다.
5. 연결 확인 → 카드 읽기 → 키 복구 → 덤프 저장이 진행됩니다.
6. **카드 교체 대기**가 나오면 원본을 치우고 대상 카드를 올립니다.
7. **교체 완료·쓰기 시작**을 누르면 쓰기 → 되읽기 검증까지 진행합니다.

화면에 현재 단계, 경과 시간, 클라이언트 출력이 실시간으로 표시됩니다. 키 복구는 수 분에서 수십 분 걸릴 수 있습니다. 쓰기 뒤 검증에 실패하면 성공으로 표시하지 않습니다.

본인 소유 또는 점검 권한이 있는 카드에만 사용하세요. 쓰기는 대상 카드 내용을 덮어씁니다.

## 준비물과 범위

- Windows 10/11 x64, Proxmark3 Easy, 데이터 USB 케이블. Python·pm3·ProxSpace 사전 설치는 필요 없습니다.
- 최초 준비에는 인터넷 연결과 약 500 MB의 여유 공간이 필요합니다. 클라이언트 다운로드는 약 42 MB, 전용 Python은 약 32 MB이며 추가 모듈도 다운로드합니다.
- 기존 Python, ProxSpace, pm3 PATH 및 예전 설정의 클라이언트·COM 경로를 기본적으로 사용하지 않습니다. Windows 업그레이드 전 설치 파일을 삭제할 필요가 없습니다. 전용 파일은 `.runtime` 안에 준비합니다.
- 자동 클라이언트 설치는 Windows x64용입니다. Linux/macOS에서는 기존 Iceman 클라이언트를 지정하세요.
- 대상은 MIFARE Classic 1K 호환 카드입니다. Gen1a 매직카드는 UID를 포함해 쓰며, 일반 카드는 UID를 바꿀 수 없습니다. 일반 카드의 인증 키·액세스 조건에 따라 쓰기가 실패할 수 있습니다. 다른 매직카드 세대 전체를 지원한다는 뜻은 아닙니다.
- 현재 쓰기 검증은 데이터 블록을 비교합니다. 일반 카드의 제조사 블록과 읽을 수 없는 섹터 키는 비교 대상에서 제외합니다. 출입 시스템 등에서 실제 사용 가능한지까지 검증하는 것은 아닙니다.

## 클라이언트 자동 준비

[Proxmark3GUI의 클라이언트 동봉·DLL 환경 설정](https://github.com/wh201906/Proxmark3GUI/blob/master/doc/tutorial/Quickstart/quickstart.md)과 [Phosphor의 단계별 카드 복제 및 실시간 출력](https://github.com/nikitaart2000/phosphor)을 참고해 구현했습니다. 다른 GUI 프로그램을 설치하거나 실행하지 않습니다.

클라이언트는 [proxmarkbuilds.org의 Easy용 RRG generic 빌드](https://www.proxmarkbuilds.org/)를 사용합니다. RDV4 빌드를 사용하지 않습니다.

- 고정 빌드: `rrg_other-20260802-da509461b734a61994f8e430e3151e9084bf9718`
- SHA-256: `4f0e94fb7ca6e81bacc7eb30635fdebb0cc18b55b39e904aeb049c1eef91d90f`
- 위치: `.runtime/<빌드>/client/proxmark3.exe`
- DLL과 사전 등 배포 파일을 함께 보관하고, 해당 프로세스에만 실행 환경을 적용합니다.
- 다운로드가 끊기거나 검증에 실패하면 설치 완료로 기록하지 않습니다. 다음 실행에서 다시 준비합니다.
- 설치된 클라이언트는 재사용합니다. 화면 조회만으로 다운로드하거나 장치를 열거하지 않습니다.

FM11RF08S 복구는 이 빌드의 [내장 `hf mf sen`](https://github.com/RfidResearchGroup/proxmark3/blob/da509461b734a61994f8e430e3151e9084bf9718/client/src/cmdhfmfsen.c)을 사용합니다. 배포 파일에 없는 Python 복구 스크립트를 호출하지 않습니다.

## Capabilities structure version 오류: Easy 펌웨어 복구

이 오류는 장치가 응답했지만 클라이언트와 장치 펌웨어의 통신 규격이 다르다는 뜻입니다. Windows 재설치나 클라이언트 재다운로드로 해결되지 않습니다.

1. `run.bat`으로 0.4.0을 받은 뒤 프로그램을 닫고 다시 실행합니다.
2. Easy 한 대만 연결하고 카드를 치웁니다.
3. 화면의 **Easy 펌웨어 복구 → Easy 펌웨어 복구 시작**에서 변경 내용을 확인하고 시작합니다.
4. 용량 확인 → 부트로더 갱신 → 용량 재확인 → 같은 빌드의 Easy 펌웨어 갱신 → 정상 연결·OS 버전 확인을 진행합니다.
5. **복구·장치 버전 확인 완료** 후 원터치 시작으로 카드를 읽습니다.

USB와 전원은 복구가 끝날 때까지 유지하세요. 부트로더 연결 실패 시 USB를 뽑고 Easy 버튼을 누른 채 연결합니다. 버튼을 놓아도 두 LED가 유지되면 놓으세요. 놓을 때 LED가 꺼지는 구형 부트로더는 쓰는 동안 누르고 있다가, 쓰기가 끝난 뒤 놓고 다시 연결해야 합니다. 본 펌웨어 쓰기는 완료됐지만 마지막 연결 확인만 실패했다면 **연결 확인**을 실행하세요. 펌웨어 쓰기를 반복할 필요는 없습니다.

복구는 정상 `hw version` 연결을 선행 조건으로 요구하지 않습니다. 공식 flasher의 구형 통신 경로를 사용하며, `--force`를 사용하지 않습니다. 이미지 없는 `--flash`로 용량을 확인할 때도 장치가 부트로더로 전환·재시작되지만 이미지는 쓰지 않습니다. 클라이언트와 같은 검증된 배포본의 `bootrom.elf`, `fullimage.elf`를 개별 SHA-256으로 확인합니다.

**동봉된 본 펌웨어는 Easy 512KB용입니다.** 256KB가 처음부터 확인되면 아무 이미지도 쓰지 않습니다. 아주 오래된 부트로더가 용량을 보고하지 못하면 공용 부트로더만 먼저 갱신하고 다시 확인합니다. 이후에도 512KB를 확인하지 못하면 본 펌웨어는 쓰지 않습니다. 256KB 장치는 별도 축소 빌드가 필요하며 이 버전은 해당 빌드를 제공하지 않습니다.

전체 로그는 `out/firmware-repair.log`에 저장됩니다. 실패한 쓰기는 자동 재시도하지 않으며, 종료 코드·완료 문구·실패 문구를 함께 확인합니다. 콘솔에서는 `run.bat flash`를 사용할 수 있습니다.

참고한 공식 절차: [RRG 부트로더 복구 안내](https://github.com/RfidResearchGroup/proxmark3/blob/master/doc/md/Installation_Instructions/Troubleshooting.md), [RRG 펌웨어 갱신·버전 일치](https://github.com/RfidResearchGroup/proxmark3/blob/master/doc/md/Use_of_Proxmark/0_Compilation-Instructions.md), [배포처 Easy 용량 및 순차 갱신 안내](https://www.proxmarkbuilds.org/). 실제 실행·성공 판정은 동봉 버전의 [flash.c](https://github.com/RfidResearchGroup/proxmark3/blob/da509461b734a61994f8e430e3151e9084bf9718/client/src/flash.c)와 [proxmark3.c](https://github.com/RfidResearchGroup/proxmark3/blob/da509461b734a61994f8e430e3151e9084bf9718/client/src/proxmark3.c)를 확인해 구현했습니다.

## 연결이 안 될 때

**자동 준비·연결 확인**으로 카드 없이 장치 버전 응답을 확인할 수 있습니다. **진단 정보**는 포트와 Windows PnP 정보를 조회합니다. 다른 pm3 프로그램이 같은 COM 포트를 사용 중이면 종료하세요.

장치 펌웨어와 클라이언트가 맞지 않으면 카드 작업을 중단하고 **Easy 펌웨어 복구**를 안내합니다. 카드 작업과 펌웨어 복구는 별도로 시작합니다. 검은 화면 문제가 다시 발생하면 반복 실행하지 말고 해당 오류와 로그를 확인하세요.

`cannot communicate with the Proxmark3`는 포트를 연 뒤 통신 검사에 실패했다는 뜻입니다. USB를 뽑고 Easy 버튼을 누르지 않은 상태로 다시 연결한 뒤 연결 확인을 한 번 실행하세요. 계속 실패하면 **통신 상세 점검**을 실행하고 `out/connection-debug.log`를 확인하세요. CLI에서는 `run.bat connect --debug`로 실행할 수 있습니다. 이 점검은 상세 출력을 켜고 `hw version`을 한 번 실행하며, 펌웨어를 쓰거나 자동 재시도하지 않습니다. 구형 펌웨어·부트로더 모드·USB 통신 문제는 추가 확인이 필요합니다. [공식 클라이언트의 통신 검사](https://github.com/RfidResearchGroup/proxmark3/blob/da509461b734a61994f8e430e3151e9084bf9718/client/src/proxmark3.c)를 기준으로 오류를 구분합니다.

- 최근 클라이언트 출력: `out/last-pm3.log`
- 저장된 덤프: `out/ams-<UID>-<시각>.bin`
- 실행한 콘솔 창을 닫으면 로컬 서버가 종료됩니다.
- 브라우저를 새로고침하면 실행 중인 작업과 카드 교체 대기 상태를 다시 표시합니다. 서버 재시작 후에는 저장된 덤프 목록에서 쓰기를 선택할 수 있습니다.

고급 사용자: 기존 클라이언트나 COM 포트를 의도적으로 사용하려면 `amsrfid.example.toml`을 `amsrfid.toml`로 복사해 설정합니다. 아래 값은 예시입니다.

```toml
use_system_client = true
pm3_path = 'C:\proxmark3\client\proxmark3.exe'
port = 'COM7'
```

## 콘솔

```text
python -m amsrfid ui         # 웹 화면
python -m amsrfid connect    # 클라이언트 자동 준비 + 연결 확인
python -m amsrfid auto       # 클라이언트 자동 준비 + 읽기
python -m amsrfid clone --from out/example.bin
python -m amsrfid diag       # 진단
python -m amsrfid version
```

## 업데이트와 테스트

`token.txt`에 GitHub 토큰이 있으면 실행 시 `claude/lucid-hamilton-2c2r4r`에서 업데이트합니다. 실행 중인 배치 파일이 변경된 경우 안내된 `run_v040.bat`을 한 번 실행하면 새 실행기로 바뀝니다. 사용자 설정, 토큰, `.runtime`, 저장 덤프는 업데이트에서 보존합니다. 0.3.2는 0.3.1 이후의 전용 Python 경로 수정과 기존 pm3 개인 설정 격리까지 포함하므로, 이미 0.3.1을 받은 경우에도 자동 업데이트됩니다.

```text
python -m pip install pytest -r requirements.txt
python -m pytest -q
python tools/check_sources.py
```

CI는 Windows·Linux에서 가상 클라이언트로 설치/연결/읽기/카드 교체/쓰기/검증 흐름을 테스트합니다. Windows에서는 실제 배포 클라이언트를 다운로드해 DLL 로딩과 SEN 도움말을 **오프라인**으로 확인합니다. 실제 USB 하드웨어 및 Windows 커널 안정성 검증은 별도입니다.

전용 Python은 [Python 공식 Windows 배포](https://www.python.org/ftp/python/3.13.12/python-3.13.12-amd64.zip)를 사용합니다. SHA-256은 `9089c1f0d720f7c913cd4caf600e6761b0a4d5b90ccf34229fe418ff64a5da5f`이며, `_pth` 파일로 전역 Python 설정 및 사용자 모듈 경로에서 격리합니다. Windows CI는 PATH에서 Python을 제거한 상태로 실제 `run.bat version`을 실행해 최초 준비를 검증합니다.
