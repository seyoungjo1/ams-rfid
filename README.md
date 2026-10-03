# ams-rfid — 필라멘트 태그 도구

핸드폰(NFC)만으로 **MIFARE Classic 1K CUID(2세대 매직/공칩)** 카드에 원하는 Bambu Lab
필라멘트 태그를 써 넣는 안드로이드 앱입니다. 별도 리더기 없이, 라이브러리에서 재질·색상을
고르고 빈 CUID 카드를 폰 뒤에 대면 됩니다. APK는 **GitHub Actions**가 빌드합니다.

> 본인이 보유한 필라멘트·장비에서의 상호운용 및 백업 용도로만 사용하세요. 이 앱은
> 비공식 커뮤니티 도구이며 어떠한 보증도 제공하지 않습니다.

참고 프로젝트:
[m0h31h31/3DPrint-Filament-RFID-Tool](https://github.com/m0h31h31/3DPrint-Filament-RFID-Tool),
[queengooborg/Bambu-Lab-RFID-Library](https://github.com/queengooborg/Bambu-Lab-RFID-Library),
[Bambu-Research-Group/RFID-Tag-Guide](https://github.com/Bambu-Research-Group/RFID-Tag-Guide).

## 요구 사항

- Android 8.0(API 26) 이상
- **NFC + MIFARE Classic 읽기/쓰기**를 지원하는 폰 (대부분의 중급 이상 기기)
- **MIFARE Classic 1K CUID(2세대) 또는 FUID 카드/스티커** — 폰으로 블록 0(UID)을 쓸 수 있는 공칩
  - 칩이 **"UID"(1세대, Gen1a)** 로 표기된 제품은 사용할 수 없습니다. 폰으로 UID를 바꿀 수 없고 AMS도 거부합니다.
  - FUID는 UID를 한 번만 쓸 수 있습니다. FUID 카드에는 앱의 "CUID 카드 점검"을 쓰지 마세요(현재 UID가 잠김).

## APK 받기

1. GitHub의 **Releases**에서 `ams-rfid-release.apk` 다운로드.
   빌드가 성공하면 `app/build.gradle.kts`의 `versionName`(예: `v1.0.0`)으로 릴리스가 자동 생성됩니다.
   같은 버전 태그가 이미 있으면 건너뛰므로, 새 릴리스를 내려면 `versionName`/`versionCode`를 올리세요.
2. 또는 **Actions** 탭 → 최근 `Build APK` 실행 → 하단 **Artifacts**의 `ams-rfid-apk`.

APK를 폰에 복사해 설치하세요(출처를 알 수 없는 앱 설치 허용 필요).

## 서명 키 (업데이트 설치용)

릴리스 APK는 저장소의 암호화된 고정 키 `keystore/release.jks.enc`로 서명됩니다. 같은 키로 서명돼야
새 버전을 기존 앱 위에 덮어 설치할 수 있습니다.

- 복호화 비밀번호는 저장소 시크릿 **`SIGNING_PASSPHRASE`** 에 둡니다
  (Settings → Secrets and variables → Actions → New repository secret).
- 시크릿이 없으면 워크플로는 임시 키로 빌드만 하고 릴리스는 게시하지 않습니다.
- 비밀번호를 잃어버리면 같은 키로 다시 서명할 수 없어 앱을 지우고 새로 설치해야 합니다. 안전한 곳에 보관하세요.

## 파일에서 굽기 (fm11rf08s 등)

라이브러리에 없는 덤프도 직접 구울 수 있습니다. **파일 굽기** 탭에서 본인이 가진 덤프 파일을 고르면 됩니다.

- 지원 형식: 원시 `.bin`(1024바이트 = 64블록), Proxmark `.json`, Flipper `.nfc`.
  FM11RF08S(= MIFARE Classic 1K 호환) 칩에서 뜬 덤프가 여기에 해당합니다. Proxmark `fm11rf08s`
  복구 결과처럼 1152바이트(72블록)인 파일은 앞 1024바이트만 씁니다.
- 파일을 고르면 UID와 (Bambu 규격이면) 필라멘트 정보를 보여주고, 빈 CUID/FUID 카드에 그대로 씁니다.
- 쓰기 엔진은 라이브러리 굽기와 동일합니다(빈 카드는 FF 키로, 반쯤 쓰인 카드는 덤프의 트레일러 키로 인증).
- 본인이 보유한 태그/카드에 대해서만, 상호운용·백업 용도로 사용하세요.

## 사용법

1. **라이브러리** 탭에서 재질·색상을 검색·선택합니다.
2. 상세 화면에서 **이 필라멘트로 카드에 쓰기**를 누릅니다.
3. 빈 CUID 카드를 폰 뒷면 NFC 위치에 대고 완료될 때까지 유지합니다.
4. 완료되면 카드를 스풀에 붙여 AMS에 넣습니다.
5. **태그 읽기** 탭에서는 기존 태그의 내용을 확인하거나, 보유한 카드가
   CUID(블록 0 재기록 가능)인지 점검할 수 있습니다.

### AMS 호환성 참고

최신 AMS 펌웨어는 일부 CUID(2세대) 태그를 감지해 블록 0에 잘못된 값을 써서 못 쓰게
만들 수 있습니다(문서상 "inconsistent / bricking"). 가장 안정적인 것은 **Gen4/FUID**
태그입니다. 자세한 내용은 위 RFID-Tag-Guide 문서를 참고하세요.

## 동작 원리

- 태그 UID로부터 HKDF-SHA256(고정 salt, `RFID-A\0`/`RFID-B\0`)로 16섹터 키를 유도합니다.
- 라이브러리 덤프(원본 UID·유도 키 포함)를 빈 CUID 카드에 그대로 복제합니다. CUID는
  블록 0(제조사/UID 블록)을 다시 쓸 수 있어 원본 UID까지 복원됩니다.
- 각 섹터는 데이터 블록을 먼저 쓰고 trailer(키/접근바이트)를 마지막에 씁니다. 이미 목표
  키로 인증되는 섹터(반쯤 기록된 카드)는 건너뛰어 멱등하게 동작합니다.

## 프로젝트 구조

```
app/src/main/java/com/ams/rfid/
  core/    UID 키 유도·덤프 파싱(라이브러리/파일)·필라멘트 정보·클론·DB비교 (순수 Kotlin, 테스트 대상)
  nfc/     android.nfc.MifareClassic → MifareCard 어댑터
  data/    DB 로더·업데이트(내장/내려받은 DB 선택, manifest 확인, 다운로드)
  ui/      Compose UI(라이브러리/파일 굽기/읽기/도움말), NFC 리더 모드
app/src/main/assets/library/index.json   빌드된 필라멘트 라이브러리
scripts/build_tag_library.py             라이브러리 덤프 → index.json 변환기
.github/workflows/build.yml              APK 빌드/릴리스 워크플로
.github/workflows/library.yml            필라멘트 DB 매일 갱신 워크플로
```

## 로컬 빌드

```sh
./gradlew testDebugUnitTest   # 코어 로직 단위 테스트
./gradlew assembleDebug       # 설치 가능한 debug APK
```

## 필라멘트 DB 자동 갱신

원본 [Bambu-Lab-RFID-Library](https://github.com/queengooborg/Bambu-Lab-RFID-Library)는 계속 태그가 추가됩니다.
앱은 APK를 다시 설치하지 않아도 새 DB를 받을 수 있습니다.

1. `.github/workflows/library.yml`이 **매일** 원본 저장소의 최신 커밋을 확인합니다. 바뀌었으면 DB를 다시 만들어
   `library-db` 릴리스에 `index.json`(DB)과 `manifest.json`(요약)을 올립니다.
2. 앱은 실행할 때 `manifest.json`을 확인합니다. 새 DB가 있으면 **추가/삭제된 색상과 함께 업데이트할지 묻습니다.**
   - **업데이트:** 내려받아 검증한 뒤 교체합니다. 실패하면 기존 DB를 그대로 씁니다.
   - **나중에:** 그 버전은 앱 시작 시 다시 묻지 않습니다. 도움말 탭의 **DB 업데이트 확인**으로 언제든 받을 수 있습니다.
3. 앱을 새 버전으로 업데이트해서 내장 DB가 더 최신이 되면 자동으로 내장 DB를 씁니다.

> 매일 자동 실행(`schedule`)과 수동 실행(`workflow_dispatch`)은 GitHub 규칙상 **기본 브랜치(main)에 워크플로 파일이 있어야** 동작합니다.
> 그 전에는 `scripts/build_tag_library.py`나 워크플로 파일이 바뀌어 푸시될 때만 DB가 게시됩니다.

직접 만들어 보려면:

```sh
git clone --depth 1 https://github.com/queengooborg/Bambu-Lab-RFID-Library.git /tmp/lib
python3 scripts/build_tag_library.py /tmp/lib app/src/main/assets/library/index.json --manifest /tmp/manifest.json
```

## 라이선스

앱 코드는 GPL-3.0을 따릅니다(참고 프로젝트와 동일). 필라멘트 태그 데이터의 저작권/라이선스는
원 출처 저장소를 따릅니다.
