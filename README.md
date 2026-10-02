# ams-rfid

Proxmark3 로 **FM11RF08S**(Fudan, MIFARE Classic 1K 호환) 카드를 **원터치**로 읽어
키를 복구하고 `.bin` 덤프로 저장하는 파이썬 도구입니다. 저장한 `.bin` 을 대상 카드에 다시
쓰는 복제도 지원합니다.

업데이트 방식과 전체 구현 방식은 자매 프로젝트 **cost-analyzer(bwbridge, SAP BW
automation)** 와 똑같이 맞췄습니다:

- 파일 하나짜리 패키지(`amsrfid/`) + `VERSION` + `run.bat`
- `token.txt` 한 줄만 두면 배포 브랜치에서 **스스로 최신본을 받아 교체**(`amsrfid/update.py`)
- `run.bat` 을 누르면 **꽂고 → 찾고 → 키 복구 → `.bin` 저장**까지 저절로 진행

---

## ⚠️ 쓰기 전에 (중요)

이 도구는 **본인이 소유하거나 명시적으로 점검 권한을 받은 카드**에만 쓰세요. 예를 들면
자기 소유 카드 백업, 보안 연구·CTF 등입니다. **남의 카드를 허락 없이 복제하는 것은 불법**
이며, 교통카드·결제카드 등의 복제는 범죄가 될 수 있습니다. 복제(쓰기)는 대상 카드의
내용을 덮어씁니다 — 되돌릴 수 없습니다.

---

## 준비물

1. **Proxmark3** (Iceman 펌웨어·클라이언트). `pm3` 명령이 PATH 에 있거나, 윈도우라면
   ProxSpace(`C:\ProxSpace\pm3\pm3.bat`) 가 설치돼 있으면 됩니다.
   - Iceman 설치: <https://github.com/RfidResearchGroup/proxmark3>
2. **파이썬 3.11 이상** (3.9~3.10 도 돌지만 설정 파일을 읽으려면 `tomli` 가 있으면 좋습니다).

이 도구는 추가 파이썬 패키지가 거의 필요 없습니다(표준 라이브러리만 사용).

## 처음 한 번 — 전체 설정 (딸깍)

Proxmark3 를 꽂고 웹 UI 의 **「⚙️ 드라이버·클라이언트·펌웨어 한 번에 설정」**(또는
`python -m amsrfid setup`) 한 번이면, **공식 Proxmark3 도구를 엮어** 필요한 것만 알아서 합니다:

1. **드라이버** — 장치는 보이는데 COM 포트가 없으면 공식 `drivers/proxmark3.inf` 를
   `pnputil` 로 설치(관리자 UAC). 이미 되어 있으면 건너뜀.
2. **클라이언트** — `proxmark3.exe`/`pm3` 를 흔한 위치에서 찾고, 없으면 **드라이브를 뒤져**
   이미 설치된 것을 찾아냅니다(찾으면 `pm3_path.txt` 에 적어 다음부턴 즉시). 정말 없으면
   설치 안내.
3. **펌웨어** — FM11RF08S 백도어를 지원 안 하는 펌웨어면 공식 `--flash` 로 fullimage 를
   올립니다(이미 지원하면 건너뜀). 부트로더(bootrom)까지 바꿔야 하면 버튼 누른 채 꽂는
   물리 단계가 한 번 필요합니다.

그다음 **「원터치 읽기」** 를 누르면 카드 읽기 → 백도어 키복구 → `.bin` 저장까지 갑니다.
(`run.bat` 은 켤 때 드라이버·클라이언트 설정을 자동으로 하고, 펌웨어 플래싱은 되돌릴 수
없으니 UI 의 '전체 설정' 버튼으로 눌러 직접 확인하며 진행하도록 두었습니다.)

## pm3 인식 / 드라이버 (Windows)

이 도구는 **공식 Proxmark3 방식 그대로** 꽂힌 장치를 자동으로 찾습니다:

- 꽂힌 COM 포트를 공식 USB VID:PID 로 자동 탐지합니다 — `9AC4:4B8F`(정품)·`2D2D:504D`(구형)·
  **`502D:502D`(Proxmark3 Easy)**. (공식 `pm3` 래퍼와 같은 PowerShell `Win32_SerialPort` 방식)
- 리눅스/맥은 udev 심링크 `/dev/pm3-*` → `/dev/ttyACM*` 순으로 봅니다.

**장치는 꽂았는데 "드라이버 필요"로 뜰 때** (특히 Proxmark3 Easy): Windows 가 아직 드라이버를
못 붙여 COM 포트가 안 생긴 상태입니다. `run.bat` 은 이 경우 **자동으로 드라이버 설치를 시도**
합니다(`driver --if-needed`, 필요할 때만 관리자권한 UAC 창). 웹 UI 의 **「드라이버 설치」** 버튼이나
`python -m amsrfid driver` 로도 됩니다. 공식 `drivers/proxmark3.inf` 를 `pnputil` 로 설치해
CDC 장치를 Windows 내장 `usbser` 에 연결 → COM 포트가 생깁니다.

클라이언트(`proxmark3.exe`/`pm3.bat`)는 PATH·ProxSpace·릴리스 폴더에서 자동으로 찾습니다.
못 찾으면 폴더에 `pm3_path.txt` 한 줄로 경로를 적거나 `amsrfid.toml` 의 `pm3_path` 를 쓰세요.

## 원터치로 쓰기 (웹 UI)

1. 이 폴더를 통째로 받습니다.
2. Proxmark3 를 USB 에 꽂습니다 (**아무것도 안 떠 있는 상태 그대로도 됩니다**).
3. `run.bat` 을 더블클릭합니다 → 브라우저에 **로컬 웹 UI**(http://127.0.0.1:8724/)가 열립니다.
4. **「꽂고 올린 카드 읽어서 .bin 저장」** 버튼을 누르고, 안내가 나오면 카드를 안테나 위에
   올립니다 — 장치 탐지 → 카드 탐지 → 종류 확인 → 키 복구 → `out\ams-<UID>-<시각>.bin`
   저장까지 진행 상황이 화면에 실시간으로 뜨며 저절로 끝납니다.
5. 저장된 덤프 목록에서 **「대상 카드에 복제」** 로 다른 카드에 쓸 수 있습니다.

웹 UI 는 이 컴퓨터 안에서만 도는 작은 서버로, `127.0.0.1` 에만 바인딩되어 외부에서는
접속할 수 없습니다. 외부 라이브러리 없이 표준 라이브러리만 쓰므로 오프라인·사내망에서도
그대로 돕니다.

콘솔로 쓰고 싶으면 `menu.bat`(번호 메뉴) 또는:

```bash
python3 -m amsrfid ui       # 웹 UI (리눅스/맥)
python3 -m amsrfid auto     # 콘솔 원터치
python3 -m amsrfid menu     # 콘솔 메뉴
```

> **배치 파일(.bat)은 일부러 영문(ASCII)만** 담았습니다. 한국어 Windows 의 cmd 는
> `.bat` 를 OEM 코드페이지로 먼저 읽어, UTF-8 한글 주석이 깨져 명령으로 잘못 실행되는
> 문제가 있습니다. 모든 한국어 안내는 UTF-8 을 제대로 다루는 Python 이 출력합니다.

## 명령어

```
python -m amsrfid            # 메뉴(번호로 고르기)
python -m amsrfid ui         # 브라우저로 쓰는 로컬 웹 UI (run.bat 기본, --port/--no-browser)
python -m amsrfid auto       # 원터치: 대기 → 키 복구 → .bin 저장
python -m amsrfid clone      # 원터치로 읽은 뒤 대상 카드에 복제
python -m amsrfid clone --from out/ams-....bin   # 그 .bin 을 대상 카드에 복제
python -m amsrfid analyze <파일.bin>   # .bin 조회: 블록0·서명·키·값·복제가능/껍데기 경고
python -m amsrfid import <파일.bin>    # 외부 .bin 을 out 폴더로 불러오기(+조회)
python -m amsrfid setup      # 전체 설정: 드라이버→클라이언트 찾기→(필요시)펌웨어 · --flash/--no-flash
python -m amsrfid driver     # Proxmark3 드라이버 설치(Windows) · --if-needed 로 필요할 때만
python -m amsrfid flash      # 펌웨어를 최신으로 플래싱(공식 --flash, fullimage)
python -m amsrfid info       # 카드 종류만 확인
python -m amsrfid update     # 배포 브랜치에서 최신본 받기 (--check 면 확인만)
python -m amsrfid version
```

- `run.bat` : 원터치(= `auto`). 더블클릭용. 인자를 주면 그대로 넘깁니다.
- `menu.bat` : 메뉴로 열기.

## 키 복구는 어떻게 되나 (백도어 원리)

FM11RF08S 는 MIFARE Classic 의 nested 공격을 막는 **정적 암호화 nonce(static encrypted
nonce)** 대응이 들어간 칩입니다. 그래서 일반 `nested`/`autopwn` 으로는 사용자 키가 안 풀립니다.

다만 Fudan 계열 전 제품에 **공개된 하드웨어 백도어 키**가 있습니다
(2024, Philippe Teuwen/Quarkslab · [IACR 2024/1275](https://eprint.iacr.org/2024/1275)):

| 칩 | 백도어 키 |
|---|---|
| FM11RF08S | `A396EFA4E24F` |
| FM11RF08 | `A31667A8CEC1` |
| FM11RF32N | `518B3354E760` |

복구 흐름(Proxmark3 Iceman `fm11rf08s_recovery` 스크립트가 하는 일):

1. **백도어 인증** — 섹터의 진짜 키를 몰라도 백도어 키로 인증해 **데이터를 읽는다**.
   단, 이때 읽히는 건 데이터일 뿐, KeyA 는 카드에서 읽히지 않는다.
2. **정적 nonce 수집** — `hf mf isen --collect_fm11rf08s_with_data` 로 섹터별 암호화 nonce 를 모은다.
3. **오프라인 솔버** — `staticnested_2x1nt_rf08s` 로 그 nonce 에서 **진짜 KeyA/KeyB 를 복구**한다
   (같은 키가 3개 이상 섹터/카드에 재사용되면 수 분 안에 풀린다).
4. 결과를 `hf-mf-<UID>-key.bin`(진짜 키) + `hf-mf-<UID>-dump.bin` 으로 떨군다.

이 도구는 FM11RF08S 가 감지되면 **`script run fm11rf08s_recovery -x -y`** 를 부르고(일반
MIFARE Classic 은 `hf mf autopwn`), 나온 `.bin` 을 `out/` 에 `ams-<UID>-<시각>.bin` 으로 보관합니다.

### ⚠️ "껍데기 키" 함정 (중요)

백도어로 **데이터만 읽은** 덤프는, 트레일러의 KeyA 자리가 진짜 키가 아니라 `FFFFFFFFFFFF`
**껍데기**로 채워져 있습니다(KeyA 는 원래 안 읽히므로). 이런 덤프를 그대로 복제하면 **원본 키가
복제되지 않습니다.** `analyze` 는 "데이터는 있는데 KeyA 가 FF 인 섹터"를 찾아 이 경우를 경고하고,
`clone` 은 기본적으로 막습니다. **먼저 백도어 복구로 진짜 키가 담긴 덤프/키 파일을 받아야** 제대로
복제됩니다. (예: 같은 카드라도 복구 전 덤프는 섹터 트레일러가 `FFFFFFFFFFFF...`, 복구 후 덤프는
`23C7F6BAE3EB...` 처럼 진짜 키가 들어 있음.)

## 복제(쓰기)

`clone` 은 `.bin`(과 진짜 키)을 대상 카드에 씁니다. `hf mf info` 로 대상 종류를 보고 방식을 고릅니다.

- **gen1a 매직카드** → `hf mf cload -f <dump>` : 인증 없이 **블록 0(UID·서명)까지 통째로** 씁니다.
  가장 확실한 복제 경로입니다(단, gen1a 는 일반 MFC 라 FM11RF08S 의 정적-nonce 동작까지
  흉내 내지는 못합니다 — 저장 내용·UID·키는 동일).
- **일반/정품 카드** → `hf mf restore --1k --uid <UID> -k <keyfile> -f <dump>` : 키 파일로 대상을
  인증해 데이터·키를 되씁니다. 제조사 블록(블록 0, UID)은 보통 못 바꿉니다.

진짜 키 소스 우선순위: `--key` 로 준 키 파일 → `out/hf-mf-<UID>-key.bin`(복구 결과) →
덤프 트레일러에서 생성. 껍데기 덤프를 데이터만이라도 gen1a 에 쓰려면 `clone --force-placeholder`.

### 블록 0 과 서명

FM11RF08S 블록 0 = UID(4) · BCC(1) · SAK(1) · ATQA(2) · 제조사 바이트(8)이고, 제조사 바이트
안에 **UID 와 묶인 서명(signature)으로 보이는 6바이트**가 들어 있습니다(정확한 생성식은 비공개).
그래서 UID 를 바꾸면 서명이 어긋나므로, 서명을 검증하는 시스템까지 속이려면 블록 0 을 **그대로**
옮겨야 하고 — 그건 블록 0 을 쓸 수 있는 매직카드(gen1a cload 등)에서만 됩니다.

## 설정 (`amsrfid.toml`, 선택)

`amsrfid.example.toml` 을 `amsrfid.toml` 로 복사해 필요한 줄만 고치세요. 전부 생략해도
기본값으로 돕니다. `amsrfid.toml` 과 `token.txt` 는 git·자동 업데이트에서 제외됩니다.

```toml
pm3_path = ""     # 비우면 PATH·ProxSpace 등에서 알아서 찾음
port     = ""     # 날것 proxmark3 를 쓸 때만
outdir   = "out"  # 덤프 저장 폴더
timeout  = 300    # 키 복구 같은 긴 명령의 제한 시간(초)
poll     = 1.5    # 장치/카드 다시 볼 간격(초)
wait     = 120    # 최대 대기(초)
```

## 자동 업데이트 (SAP BW automation 과 동일)

폴더에 `token.txt`(GitHub 개인 액세스 토큰 한 줄, 비공개 저장소라 `repo` 권한 필요)를 두면,
`run.bat` 이 돌 때마다 배포 브랜치(`claude/lucid-hamilton-2c2r4r`)의 `VERSION` 을 확인해
새 버전이면 파일을 통째로 받아 교체합니다.

- 브랜치를 **SHA 로 고정**해 받아, 받는 도중 새 커밋이 올라와도 뒤섞이지 않습니다.
- **전부 받은 뒤에야** 교체하고, 바꾸기 전에 `backup/<시각>/` 로 백업합니다.
- 받은 파일끼리 실제로 맞물리는지 자식 파이썬으로 한 번 임포트해 보고, 아니면 버전을 안 올립니다.
- 사용자 것(`token.txt`·`amsrfid.toml`·`out`·`venv`·`backup`)은 건드리지 않습니다.
- 지금 돌고 있는 `run.bat` 만 못 덮어쓰므로 옆에 `run_v<버전>.bat` 으로 받아 두고, 그 파일을
  한 번 실행하면 자기를 원본으로 되돌립니다(self-heal).

## 폴더 구조

```
amsrfid/
  __main__.py   cli.py      # 진입점·명령줄
  web.py        ui.html     # 로컬 웹 UI(서버 + 화면)
  menu.py                   # 번호로 고르는 콘솔 메뉴
  workflow.py               # 원터치 흐름(대기→확인→복구→저장) + 복제
  pm3.py                    # Proxmark3 클라이언트 찾기·실행
  dump.py                   # .bin(MIFARE Classic 1K) 읽기·저장, 출력 파싱
  config.py                 # amsrfid.toml 읽기
  update.py                 # token.txt 기반 자가 갱신
VERSION  run.bat  menu.bat  pyproject.toml  amsrfid.example.toml
tests/                      # pytest 테스트
```

## 테스트

```bash
pip install pytest
pytest -q
```

하드웨어 없이도 가짜 pm3(`tests/fakes.py`)로 흐름 전체를 검증합니다.
