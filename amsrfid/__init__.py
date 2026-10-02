"""ams-rfid — Proxmark3 로 FM11RF08S 를 원터치로 읽고·복원하는 도구.

cost-analyzer(bwbridge)의 SAP BW automation 과 같은 방식으로 짰다:
  · 파일 하나짜리 패키지(amsrfid/) + VERSION + run.bat
  · token.txt 한 줄이면 배포 브랜치에서 스스로 최신본을 받아 교체(update.py)
  · run.bat 이 원터치로 '꽂으면 → 찾고 → 키 복구 → .bin 저장' 까지 쭉 진행

이 도구는 **본인 소유의 카드**(출입증 백업, 사내 출입관리 시스템 점검, 보안 연구·CTF 등
권한이 있는 대상)에만 쓰는 것을 전제로 한다. 남의 카드를 허락 없이 복제하는 것은 불법이다.
"""
from __future__ import annotations

__all__ = ["__version__"]


def _read_version() -> str:
    from pathlib import Path

    try:
        return (Path(__file__).resolve().parent.parent / "VERSION").read_text(
            encoding="utf-8-sig"
        ).strip() or "0"
    except OSError:
        return "0"


__version__ = _read_version()
