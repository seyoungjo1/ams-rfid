"""Install a pinned portable Windows client; keep DLLs/resources beside it.

Packaging/environment approach: Proxmark3GUI's preload documentation.
Binaries: Gator96100's proxmarkbuilds.org RRG generic (Easy) distribution.
No drivers, registry edits or device flashing are performed here.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit, urlunsplit

from .pm3 import Pm3Error

BUILD = "rrg_other-20260802-da509461b734a61994f8e430e3151e9084bf9718"
SHA256 = "4f0e94fb7ca6e81bacc7eb30635fdebb0cc18b55b39e904aeb049c1eef91d90f"
LOCATOR = "https://www.proxmarkbuilds.org/latest/rrg_other.php"
STORAGE = "u533973-sub1.your-storagebox.de"
MAX_DOWNLOAD = 256 * 1024 * 1024
_LOCK = threading.Lock()


def runtime_dir(root: Path) -> Path:
    return root / ".runtime" / BUILD


def installed_client(root: Path) -> str | None:
    base = runtime_dir(root)
    client = base / "client" / "proxmark3.exe"
    try:
        manifest = json.loads((base / "installed.json").read_text(encoding="utf-8"))
        if manifest.get("sha256") == SHA256 and client.is_file() and (client.parent / "libs").is_dir():
            return str(client.resolve())
    except (OSError, ValueError):
        pass
    return None


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _asset_request() -> urllib.request.Request:
    # The publisher currently advertises its public storage login in a redirect.
    # Resolve it at runtime, never persist/log it, and pin the filename and digest.
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(LOCATOR, timeout=30):
            raise Pm3Error("클라이언트 배포 주소 형식이 변경되었습니다. 프로그램 업데이트가 필요합니다.")
    except urllib.error.HTTPError as e:
        if e.code not in (301, 302, 303, 307, 308):
            raise
        location = e.headers.get("Location", "")
        e.close()
    target = urlsplit(location)
    if target.scheme != "https" or target.hostname != STORAGE or not target.username or not target.password:
        raise Pm3Error("클라이언트 배포 서버를 확인하지 못했습니다.")
    url = urlunsplit(("https", STORAGE, "/rrg_other/" + BUILD + ".7z", "", ""))
    login = (unquote(target.username) + ":" + unquote(target.password)).encode()
    return urllib.request.Request(url, headers={
        "Authorization": "Basic " + base64.b64encode(login).decode("ascii"),
        "User-Agent": "ams-rfid-portable-installer",
    })


def _download(dest: Path, echo) -> None:
    request = _asset_request()
    # No redirects here: the public storage login belongs to this host only.
    with urllib.request.build_opener(_NoRedirect).open(request, timeout=60) as response, dest.open("wb") as out:
        total = int(response.headers.get("Content-Length") or 0)
        count, last = 0, -1
        digest = hashlib.sha256()
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            count += len(chunk)
            if count > MAX_DOWNLOAD:
                raise Pm3Error("클라이언트 다운로드 크기가 제한을 초과했습니다.")
            digest.update(chunk)
            out.write(chunk)
            percent = count * 100 // total if total else 0
            if percent // 10 != last:
                echo("다운로드 %s%% · %.1f MB" % (percent, count / 1024 / 1024))
                last = percent // 10
    if digest.hexdigest() != SHA256:
        raise Pm3Error("클라이언트 파일 검증 실패. 설치하지 않았습니다. 다시 준비를 실행하세요.")


def _extract(archive: Path, dest: Path) -> None:
    try:
        import py7zr
    except ImportError:
        raise Pm3Error("압축 해제 모듈이 없습니다. run.bat 을 다시 실행하세요.") from None
    with py7zr.SevenZipFile(archive) as bundle:
        entries = bundle.list()
        if sum(entry.uncompressed or 0 for entry in entries) > 1024 * 1024 * 1024:
            raise Pm3Error("압축 해제 크기 제한을 초과했습니다.")
        for entry in entries:
            path = PurePosixPath(entry.filename.replace("\\", "/"))
            if path.is_absolute() or ".." in path.parts or ":" in str(path) or getattr(entry, "is_symlink", False):
                raise Pm3Error("올바르지 않은 클라이언트 압축 경로입니다.")
        bundle.extractall(dest)


def supported_platform() -> bool:
    return os.name == "nt" and platform.machine().lower() in ("amd64", "x86_64")


def ensure_extractor(echo) -> None:
    try:
        import py7zr
    except ImportError:
        echo("압축 해제 모듈을 준비하는 중… (최초 1회)")
        done = subprocess.run([sys.executable, "-m", "pip", "install", "py7zr>=1.0,<2"],
                              capture_output=True, timeout=180)
        if done.returncode:
            raise Pm3Error("압축 해제 모듈 설치에 실패했습니다. run.bat 의 설치 메시지를 확인하세요.")


def install(root: Path, echo=print) -> str:
    with _LOCK:
        existing = installed_client(root)
        if existing:
            echo("클라이언트 준비됨 (설치된 휴대용 버전 사용)")
            return existing
        if not supported_platform():
            raise Pm3Error("자동 클라이언트 설치는 Windows x64용입니다. 다른 환경은 pm3_path 를 지정하세요.")
        root.mkdir(parents=True, exist_ok=True)
        parent = root / ".runtime"
        parent.mkdir(exist_ok=True)
        try:
            with tempfile.TemporaryDirectory(prefix="install-", dir=parent) as temp:
                stage = Path(temp)
                archive, unpacked = stage / "client.7z", stage / "unpacked"
                echo("Easy용 클라이언트 다운로드 시작 (약 42 MB, 최초 1회)")
                ensure_extractor(echo)
                _download(archive, echo)
                echo("파일 검증 완료 · 클라이언트와 DLL 압축 해제 중…")
                _extract(archive, unpacked)
                client = unpacked / "client" / "proxmark3.exe"
                if not client.is_file() or not (client.parent / "libs").is_dir():
                    raise Pm3Error("클라이언트 패키지 구성이 올바르지 않습니다.")
                (unpacked / "installed.json").write_text(json.dumps({
                    "build": BUILD, "sha256": SHA256, "source": LOCATOR,
                }), encoding="utf-8")
                target = runtime_dir(root)
                if target.exists():
                    shutil.rmtree(target)
                unpacked.rename(target)
        except Pm3Error:
            raise
        except Exception as e:
            # URL errors may include the publisher's public storage credentials.
            raise Pm3Error("클라이언트 준비 실패 (%s). 인터넷 연결을 확인하고 다시 실행하세요." % type(e).__name__) from None
        echo("클라이언트 설치 완료")
        return str((runtime_dir(root) / "client" / "proxmark3.exe").resolve())


def client_environment(client: str) -> dict[str, str]:
    env = os.environ.copy()
    libs = Path(client).resolve().parent / "libs"
    if libs.is_dir():
        # Use packaged libraries and Windows system tools, not an old ProxSpace PATH.
        windows = Path(env.get("SystemRoot", r"C:\Windows"))
        tail = os.pathsep.join([str(windows / "System32"), str(windows)]) if os.name == "nt" else env.get("PATH", "")
        env["PATH"] = os.pathsep.join([str(libs), str(libs / "shell"), tail])
        env["QT_PLUGIN_PATH"] = str(libs)
        env["QT_QPA_PLATFORM_PLUGIN_PATH"] = str(libs)
        env["MSYSTEM"] = "MINGW64"
    return env
