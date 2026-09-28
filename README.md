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
- **MIFARE Classic 1K CUID(2세대) 매직 카드** — 블록 0 재기록이 가능한 공칩

## APK 받기

1. GitHub의 **Releases**에서 `ams-rfid-release.apk` 다운로드.
   빌드가 성공하면 `app/build.gradle.kts`의 `versionName`(예: `v1.0.0`)으로 릴리스가 자동 생성됩니다.
   같은 버전 태그가 이미 있으면 건너뛰므로, 새 릴리스를 내려면 `versionName`/`versionCode`를 올리세요.
2. 또는 **Actions** 탭 → 최근 `Build APK` 실행 → 하단 **Artifacts**의 `ams-rfid-apk`.

APK를 폰에 복사해 설치하세요(출처를 알 수 없는 앱 설치 허용 필요).

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
  core/    UID 키 유도·덤프 파싱·필라멘트 정보·클론 로직 (순수 Kotlin, 단위 테스트 대상)
  nfc/     android.nfc.MifareClassic → MifareCard 어댑터
  data/    assets/library/index.json 로더
  ui/      Compose UI, NFC 리더 모드 액티비티
app/src/main/assets/library/index.json   빌드된 필라멘트 라이브러리
scripts/build_tag_library.py             라이브러리 덤프 → index.json 변환기
.github/workflows/build.yml              APK 빌드/릴리스 워크플로
```

## 로컬 빌드

```sh
./gradlew testDebugUnitTest   # 코어 로직 단위 테스트
./gradlew assembleDebug       # 설치 가능한 debug APK
```

## 라이브러리 갱신

```sh
git clone --depth 1 https://github.com/queengooborg/Bambu-Lab-RFID-Library.git /tmp/lib
python3 scripts/build_tag_library.py /tmp/lib app/src/main/assets/library/index.json
```

## 라이선스

앱 코드는 GPL-3.0을 따릅니다(참고 프로젝트와 동일). 필라멘트 태그 데이터의 저작권/라이선스는
원 출처 저장소를 따릅니다.
