#!/usr/bin/env python3
"""소스 무결성 가드 — CI 에서 돈다.

사용자 PC 에서 pm3.py 가 '널 바이트'로 깨져 죽은 사고가 있었다. 그 종류의 손상을
커밋 단계에서 잡는다: 모든 .py 가 (1) 널 바이트가 없고 (2) 유효한 UTF-8 이며
(3) 파이썬으로 컴파일되는지 확인한다.
"""
from __future__ import annotations

import glob
import sys


def main() -> int:
    bad: list[str] = []
    files = sorted(glob.glob("amsrfid/*.py") + glob.glob("tests/**/*.py", recursive=True)
                   + glob.glob("tools/*.py"))
    for f in files:
        data = open(f, "rb").read()
        if b"\x00" in data:
            bad.append("%s: 널 바이트 포함" % f)
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as e:
            bad.append("%s: UTF-8 아님 (%s)" % (f, e))
            continue
        try:
            compile(text, f, "exec")
        except SyntaxError as e:
            bad.append("%s: 컴파일 실패 (%s)" % (f, e))
    if bad:
        print("소스 무결성 실패:")
        for b in bad:
            print("  · " + b)
        return 1
    print("OK: %d개 .py 모두 널 바이트 없음 · 유효 UTF-8 · 컴파일 성공" % len(files))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
