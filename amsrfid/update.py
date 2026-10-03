"""token.txt 로 스스로 갱신하기 (cost-analyzer/bwbridge 와 똑같은 방식).

폴더에 token.txt(GitHub 개인 액세스 토큰 한 줄)를 두면, 배포 브랜치의 VERSION 을 확인해
새 버전이면 파일을 통째로 내려받아 교체한다. 사내에서 git 을 못 써도 최신본을 받을 수 있다.

원칙
  · 브랜치를 SHA 로 고정해 받는다 — 받는 도중 새 커밋이 올라와도 뒤섞이지 않는다.
  · 전부 받은 뒤에야 교체한다 — 중간에 실패하면 아무것도 안 바꾼다.
  · 바꾸기 전에 backup/<시각>/ 로 백업한다.
  · 사용자 것(token.txt·amsrfid.toml·out·venv·backup)은 절대 건드리지 않는다.
  · **지금 돌고 있는** run.bat 만 덮어쓸 수 없으므로 run_v<버전>.bat 로 떨어뜨린다.
    run.bat 첫머리의 self-heal 줄이 그 파일을 실행하면 자기를 원본으로 되돌린다.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
REPO = "seyoungjo1/ams-rfid"
BRANCH = "claude/lucid-hamilton-2c2r4r"
API = "https://api.github.com"

EXCLUDE_EXACT = {"token.txt", "amsrfid.toml", "ams-rfid.toml"}
EXCLUDE_PREFIX = ("out/", "venv", ".venv", "backup/", "__pycache__/", ".git/", "tests/")


class UpdateError(Exception):
    pass


def read_token(root: Path | None = None) -> str:
    p = (root or ROOT) / "token.txt"
    try:
        return p.read_text(encoding="utf-8-sig").strip()
    except OSError:
        return ""


def local_version(root: Path | None = None) -> str:
    try:
        return ((root or ROOT) / "VERSION").read_text(encoding="utf-8-sig").strip() or "0"
    except OSError:
        return "0"


def _get(path: str, token: str, raw: bool = False, timeout: float = 30) -> bytes:
    req = urllib.request.Request(
        API + path,
        headers={
            "Authorization": "Bearer " + token,
            "X-GitHub-Api-Version": "2022-11-28",
            "Accept": "application/vnd.github.raw" if raw else "application/vnd.github+json",
            "User-Agent": "amsrfid-updater",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ssl.create_default_context()) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise UpdateError("토큰이 유효하지 않거나 권한이 없습니다 (HTTP %d). token.txt 를 확인하세요." % e.code) from None
        if e.code == 404:
            raise UpdateError("찾지 못했습니다 (HTTP 404): %s" % path) from None
        raise UpdateError("GitHub 오류 HTTP %d: %s" % (e.code, path)) from None


def branch_sha(token: str, branch: str = BRANCH) -> str:
    data = json.loads(_get("/repos/%s/branches/%s" % (REPO, quote(branch)), token))
    sha = (data.get("commit") or {}).get("sha")
    if not sha:
        raise UpdateError("브랜치 %s 의 커밋을 찾지 못했습니다" % branch)
    return sha


def remote_version(token: str, sha: str) -> str:
    return _get("/repos/%s/contents/VERSION?ref=%s" % (REPO, sha), token, raw=True).decode("utf-8").strip()


def is_excluded(path: str) -> bool:
    return path in EXCLUDE_EXACT or path.startswith(EXCLUDE_PREFIX)


def list_paths(tree: dict[str, Any]) -> list[str]:
    if tree.get("truncated"):
        raise UpdateError("저장소가 너무 커서 파일 목록이 잘렸습니다(truncated)")
    out = []
    for t in tree.get("tree", []):
        p = t.get("path", "")
        if t.get("type") == "blob" and p and not is_excluded(p):
            out.append(p)
    return out


def _blob_ok(path: str, data: bytes) -> bool:
    """받은 .py 가 온전한지 — 널 바이트/인코딩 손상/빈 파일을 걸러낸다.

    (사용자 PC 에서 pm3.py 가 널 바이트로 깨져 'source code string cannot contain null bytes'
    로 죽은 사례가 있어, 깨진 걸 아예 안 쓰게 막는다.)
    """
    if path.endswith(".py"):
        if not data or b"\x00" in data:
            return False
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            return False
    return True


def download(token: str, sha: str, progress: Any = None) -> dict[str, bytes]:
    tree = json.loads(_get("/repos/%s/git/trees/%s?recursive=1" % (REPO, sha), token))
    paths = list_paths(tree)
    blobs: dict[str, bytes] = {}
    for i, p in enumerate(paths, 1):
        data = _get("/repos/%s/contents/%s?ref=%s" % (REPO, quote(p), sha), token, raw=True)
        if not _blob_ok(p, data):
            data = _get("/repos/%s/contents/%s?ref=%s" % (REPO, quote(p), sha), token, raw=True)  # 한 번 재시도
            if not _blob_ok(p, data):
                raise UpdateError(
                    "받은 파일이 손상됐습니다(널 바이트/인코딩): %s — 업데이트를 중단하고 기존 파일을 "
                    "그대로 둡니다. 잠시 뒤 다시 시도하세요." % p)
        blobs[p] = data
        if progress:
            progress(i, len(paths), p)
    return blobs


IMPORT_PROBE = """\
import sys, importlib
sys.path.insert(0, sys.argv[1])
for m in sys.argv[2:]:
    try:
        importlib.import_module(m)
    except ModuleNotFoundError as e:
        if (getattr(e, "name", "") or "").split(".")[0] != "amsrfid":
            continue          # 우리 것이 아닌 부품이 빠진 것 — 업데이트를 막을 일이 아니다
        sys.stderr.write("%s: %s\\n" % (m, e))
        raise SystemExit(1)
    except ImportError as e:
        sys.stderr.write("%s: %s\\n" % (m, e))
        raise SystemExit(1)
    except Exception:
        pass                  # 임포트는 됐는데 딴 이유로 화내는 것은 여기서 볼 일이 아니다
"""


def import_check(blobs: dict[str, bytes], root: Path) -> list[str]:
    """받은 파일끼리 실제로 맞물리는지 자식 파이썬으로 한 번 임포트해 본다."""
    names = {str(rel).replace("\\", "/") for rel in blobs}
    if "amsrfid/__init__.py" not in names or not sys.executable:
        return []
    mods = ["amsrfid"]
    for rel in sorted(names):
        if not rel.startswith("amsrfid/") or not rel.endswith(".py"):
            continue
        stem = rel[len("amsrfid/"):-3]
        if "/" in stem or stem.startswith("__") or not stem.isidentifier():
            continue
        mods.append("amsrfid." + stem)
    try:
        done = subprocess.run([sys.executable, "-c", IMPORT_PROBE, str(root)] + mods,
                              cwd=str(root), capture_output=True, timeout=180)
    except (OSError, subprocess.SubprocessError):
        return []
    if done.returncode == 0:
        return []
    tail = (done.stderr or b"").decode("utf-8", "replace").strip().splitlines()
    return ["새 파일끼리 맞물리지 않습니다: %s" % (tail[-1].strip() if tail else "임포트 실패")]


ALT_BAT = re.compile(r"^(.*)_v\d+\.bat$", re.I)


def running_bat() -> str:
    """지금 돌고 있어서 덮어쓸 수 없는 배치 파일의 이름."""
    name = (os.environ.get("AMSRFID_RUNNING_BAT") or "").strip().replace("\\", "/").rstrip("/")
    return (name.rsplit("/", 1)[-1] or "run.bat").lower()


def sweep_alt_bats(root: Path, keep: set[str]) -> list[str]:
    """원본과 내용이 같아진 <이름>_v<버전>.bat 잔해를 지운다 (self-heal 이 끝난 것들)."""
    gone = []
    for alt in sorted(root.glob("*_v*.bat")):
        m = ALT_BAT.match(alt.name)
        if not m or alt.name in keep:
            continue
        orig = alt.with_name(m.group(1) + ".bat")
        try:
            if orig.is_file() and orig.read_bytes() == alt.read_bytes():
                alt.unlink()
                gone.append(alt.name)
        except OSError:
            pass
    return gone


def apply(blobs: dict[str, bytes], version: str, root: Path | None = None) -> dict[str, list[str]]:
    """백업 후 교체. 실행 중인 run.bat 은 새 이름으로 떨어뜨린다."""
    root = root or ROOT
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = root / "backup" / stamp
    result: dict[str, list[str]] = {"changed": [], "same": [], "deferred": [], "failed": [], "backup": [str(backup)]}
    running = running_bat()
    put_off: set[str] = set()
    for rel, data in sorted(blobs.items()):
        if rel == "VERSION":
            continue  # Commit the version only after every file and import check succeeds.
        dest = root / rel
        try:
            old = dest.read_bytes() if dest.is_file() else None
            if old == data:
                result["same"].append(rel)
                continue
            if old is not None:
                b = backup / rel
                b.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(dest, b)
            if dest.name.lower() == running and old is not None:
                alt = dest.with_name("%s_v%s.bat" % (dest.stem, version.replace(".", "")))
                alt.write_bytes(data)
                result["deferred"].append(str(alt.name))
                put_off.add(rel)
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            result["changed"].append(rel)
        except OSError as e:
            result["failed"].append("%s (%s)" % (rel, e))
    for rel, data in sorted(blobs.items()):
        if rel == "VERSION":
            continue  # Commit the version only after every file and import check succeeds.
        dest = root / rel
        if rel in put_off:
            continue
        try:
            if dest.read_bytes() != data:
                result["failed"].append("%s (내용이 다릅니다)" % rel)
        except OSError as e:
            result["failed"].append("%s (%s)" % (rel, e))
    clear_pycache(root)
    result["swept"] = sweep_alt_bats(root, set(result["deferred"]))
    if not result["failed"]:
        result["failed"] += import_check(blobs, root)
    if result["failed"]:
        return result
    (root / "VERSION").write_text(version, encoding="utf-8")
    return result


def clear_pycache(root: Path) -> int:
    n = 0
    for d in root.rglob("__pycache__"):
        try:
            shutil.rmtree(d)
            n += 1
        except OSError:
            pass
    return n


def run(check_only: bool = False, root: Path | None = None, echo: Any = print) -> int:
    root = root or ROOT
    token = read_token(root)
    if not token:
        echo("token.txt 가 없습니다. GitHub 토큰을 한 줄로 넣어 두면 자동 갱신이 켜집니다.")
        echo("  (비공개 저장소라 'repo' 권한이 있는 토큰이 필요합니다. 이 파일은 git 에 올라가지 않습니다.)")
        return 0
    here = local_version(root)
    try:
        sha = branch_sha(token)
        there = remote_version(token, sha)
    except UpdateError as e:
        echo("업데이트 확인 실패: %s" % e)
        return 0 if not check_only else 1
    except Exception as e:
        echo("업데이트 확인 실패 (%s) — 기존 파일로 진행합니다." % e.__class__.__name__)
        return 0
    if there == here:
        echo("최신 버전입니다 (v%s)." % here)
        return 0
    echo("업데이트: v%s → v%s" % (here, there))
    if check_only:
        return 1
    blobs = download(token, sha, progress=lambda i, n, p: echo("  [%d/%d] %s" % (i, n, p)))
    res = apply(blobs, there, root)
    echo("바뀐 파일 %d개 · 그대로 %d개 · 백업 %s" % (len(res["changed"]), len(res["same"]), res["backup"][0]))
    for name in res["deferred"]:
        echo("  * 지금 돌고 있어 바꾸지 못한 %s 는 옆에 받아 두었습니다 — 그 파일을 한 번 실행하면 원본이 갱신됩니다." % name)
    if res.get("failed"):
        echo("")
        echo("바꾸지 못한 파일이 %d개 있습니다 — 버전은 v%s 그대로 둡니다." % (len(res["failed"]), here))
        for line in res["failed"][:10]:
            echo("  · %s" % line)
        return 1
    echo("업데이트 완료 (v%s). 검은 창을 닫고 run.bat 을 다시 실행하세요." % there)
    return 0


# 패키지가 깨졌을 때(예: pm3.py 널 바이트)도 스스로 복구할 수 있게 단독 실행을 지원한다.
# 이 모듈은 amsrfid 내부 모듈을 import 하지 않으므로, 다른 파일이 손상돼도 돌아간다.
#   python -m amsrfid.update        → 깨진 파일을 깨끗한 최신본으로 다시 받아 복구
if __name__ == "__main__":
    import sys as _sys
    raise SystemExit(run(check_only=False))
