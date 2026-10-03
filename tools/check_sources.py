#!/usr/bin/env python3
"""Source integrity guard — runs in CI.

A user's pm3.py once got corrupted with NUL bytes ('source code string cannot
contain null bytes') and crashed on import. This catches that class of damage at
commit time: every .py must (1) have no NUL bytes, (2) be valid UTF-8, and
(3) compile.

Output is ASCII-only on purpose so it prints fine on a Windows console (cp1252).
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
            bad.append("%s: contains NUL byte(s)" % f)
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as e:
            bad.append("%s: not valid UTF-8 (%s)" % (f, e))
            continue
        try:
            compile(text, f, "exec")
        except SyntaxError as e:
            bad.append("%s: does not compile (%s)" % (f, e))
    if bad:
        print("SOURCE INTEGRITY FAILED:")
        for b in bad:
            print("  - " + b)
        return 1
    print("OK: %d .py files: no NUL bytes, valid UTF-8, all compile" % len(files))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
