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
자기 출입증 백업, 사내 출입관리 시스템(AMS)의 보안 점검, 보안 연구·CTF 등입니다.
**남의 카드를 허락 없이 복제하는 것은 불법**이며, 교통카드·결제카드 등의 복제는 범죄가
될 수 있습니다. 복제(쓰기)는 대상 카드의 내용을 덮어씁니다 — 되돌릴 수 없습니다.

---

## 준비물

1. **Proxmark3** (Iceman 펌웨어·클라이언트). `pm3` 명령이 PATH 에 있거나, 윈도우라면
   ProxSpace(`C:\ProxSpace\pm3\pm3.bat`) 가 설치돼 있으면 됩니다.
   - Iceman 설치: <https://github.com/RfidResearchGroup/proxmark3>
2. **파이썬 3.11 이상** (3.9~3.10 도 돌지만 설정 파일을 읽으려면 `tomli` 가 있으면 좋습니다).

이 도구는 추가 파이썬 패키지가 거의 필요 없습니다(표준 라이브러리만 사용).

## 원터치로 쓰기

1. 이 폴더를 통째로 받습니다.
2. Proxmark3 를 USB 에 꽂습니다 (**아무것도 안 떠 있는 상태 그대로도 됩니다**).
3. `run.bat` 을 더블클릭합니다.
4. 안내대로 카드를 안테나 위에 올리면 — 장치 탐지 → 카드 탐지 → 종류 확인 →
   키 복구 → `out\ams-<UID>-<시각>.bin` 저장까지 저절로 진행됩니다.

리눅스·맥이면:

```bash
python3 -m amsrfid auto
```

## 명령어

```
python -m amsrfid            # 메뉴(번호로 고르기)
python -m amsrfid auto       # 원터치: 대기 → 키 복구 → .bin 저장
python -m amsrfid clone      # 원터치로 읽은 뒤 대상 카드에 복제
python -m amsrfid clone --from out/ams-....bin   # 그 .bin 을 대상 카드에 복제
python -m amsrfid info       # 카드 종류만 확인
python -m amsrfid update     # 배포 브랜치에서 최신본 받기 (--check 면 확인만)
python -m amsrfid version
```

- `run.bat` : 원터치(= `auto`). 더블클릭용. 인자를 주면 그대로 넘깁니다.
- `menu.bat` : 메뉴로 열기.

## 키 복구는 어떻게 하나

FM11RF08S 는 MIFARE Classic 의 nested 공격을 막는 **정적 암호화 nonce** 대응이 들어간
칩입니다. 다만 Fudan 계열에 공개된 **백도어 키**(`A396EFA4E24F`, 2024 Teuwen 연구)가 있어,
Proxmark3 Iceman 의 `hf mf autopwn` 이 이를 활용해 전 섹터 키를 복구하고 덤프까지 떨굽니다.
이 도구는 그 `hf mf autopwn` 을 불러 결과 `.bin` 을 `out/` 에 보관합니다.

`autopwn` 이 일부 섹터를 못 풀면, pm3 에 들어 있는 전용 복구 스크립트로 다시 시도하라고
안내합니다:

```
pm3 셸에서:  script run fm11rf08s_recovery
```

## 복제(쓰기)

떠 둔 `.bin` 을 대상 카드에 씁니다. 대상 카드 종류를 `hf mf info` 로 보고 방식을 고릅니다.

- **매직 카드(gen1a 등)** : `hf mf cload` 로 블록 0(UID)까지 통째로 씁니다 — UID 까지 똑같이
  만들 수 있습니다.
- **일반/정품 FM11RF08S** : `hf mf restore` 로 덤프 안 트레일러의 키를 써서 블록을 되씁니다.
  제조사 블록(블록 0, UID)은 보통 못 바꿉니다.

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
  menu.py                   # 번호로 고르는 메뉴
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
