"""로컬 웹 UI — 브라우저에서 버튼으로 쓰는 화면.

하드웨어(Proxmark3)를 다루므로 claude.ai 같은 원격이 아니라, 이 컴퓨터 안에서만 도는
작은 서버다. 127.0.0.1 에만 바인딩해 외부에서는 접속할 수 없다. 외부 의존성 없이
표준 라이브러리(http.server)만 쓴다 — 사내망·오프라인에서도 그대로 돈다.

구조
  · 작업(Job)은 한 번에 하나(하드웨어가 하나라서). 백그라운드 스레드에서 돌고,
    진행 로그를 쌓아 둔다. 화면은 /api/job 을 짧게 폴링해 새 줄만 받아 보여 준다.
  · workflow.* 함수의 echo 콜백을 작업 로그에 꽂아, 콘솔과 똑같은 진행 메시지를 쓴다.
"""
from __future__ import annotations

import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable

from . import __version__, dump as D, update, workflow
from .config import Config
from .pm3 import Pm3, Pm3Error

HERE = Path(__file__).resolve().parent
UI_HTML = HERE / "ui.html"


class Job:
    """지금 돌고 있는(또는 방금 끝난) 작업 하나."""

    def __init__(self, kind: str):
        self.kind = kind
        self.lines: list[str] = []
        self.running = True
        self.ok = False
        self.error = ""
        self.result: dict[str, Any] = {}
        self._lock = threading.Lock()

    def log(self, msg: str) -> None:
        with self._lock:
            for part in str(msg).split("\n"):
                self.lines.append(part)

    def snapshot(self, since: int) -> dict[str, Any]:
        with self._lock:
            return {
                "kind": self.kind,
                "running": self.running,
                "ok": self.ok,
                "error": self.error,
                "result": self.result,
                "total": len(self.lines),
                "lines": self.lines[since:],
            }


class App:
    """설정과 현재 작업을 쥐고 있는 알맹이. 핸들러가 이걸 통해 일한다."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.job: Job | None = None
        self._lock = threading.Lock()

    # -- 상태/목록 ---------------------------------------------------------

    def status(self) -> dict[str, Any]:
        import time as _t
        from .pm3 import detect_device
        info: dict[str, Any] = {"version": __version__, "outdir": str(self.cfg.out_path)}
        try:
            pm3 = Pm3.locate(self.cfg.pm3_path or None, self.cfg.port or None, self.cfg.out_path)
            info["pm3"] = pm3.client
        except Pm3Error as e:
            info["pm3"] = None
            info["pm3_error"] = str(e)
        # 꽂힌 장치/포트/드라이버 상태를 공식 VID:PID 로 탐지. 가볍게 캐시해 폴링 부담을 줄인다.
        now = _t.monotonic()
        if now - getattr(self, "_dev_at", 0) > 3:
            self._dev = detect_device()
            if self.cfg.port:
                self._dev["com"] = self.cfg.port
            self._dev_at = now
        dev = getattr(self, "_dev", {})
        info["port"] = dev.get("com")
        info["device_present"] = dev.get("present", False)
        info["needs_driver"] = dev.get("needs_driver", False)
        info["device_name"] = dev.get("name", "")
        return info

    def install_driver(self) -> dict[str, Any]:
        from .pm3 import install_driver
        ok, msg = install_driver()
        self._dev_at = 0           # 상태 캐시를 비워 다음 status 에서 다시 본다
        return {"ok": ok, "message": msg}

    def dumps(self) -> list[dict[str, Any]]:
        out = self.cfg.out_path
        if not out.is_dir():
            return []
        items = []
        for p in sorted(out.glob("*.bin"), key=lambda p: p.stat().st_mtime, reverse=True):
            st = p.stat()
            items.append({"name": p.name, "size": st.st_size, "mtime": int(st.st_mtime)})
        return items

    def import_bin(self, name: str, data: bytes) -> dict[str, Any]:
        """외부 .bin 을 out/ 으로 불러온다(업로드). 크기를 먼저 확인한다."""
        import os as _os
        if len(data) not in (D.SIZE_1K, 4096):
            return {"ok": False, "error": "크기가 %d바이트입니다 — 1024(1K) 또는 4096(4K)만 됩니다." % len(data)}
        safe = _os.path.basename((name or "").replace("\\", "/")) or "imported.bin"
        if not safe.lower().endswith(".bin"):
            safe += ".bin"
        self.cfg.out_path.mkdir(parents=True, exist_ok=True)
        dest = self.cfg.out_path / safe
        dest.write_bytes(data)
        return {"ok": True, "name": safe}

    def analyze_dump(self, name: str) -> dict[str, Any]:
        """out/ 의 .bin 하나를 조회(블록0·키·값·복제가능)."""
        import os as _os
        safe = _os.path.basename((name or "").replace("\\", "/"))
        src = self.cfg.out_path / safe
        if not src.is_file():
            return {"ok": False, "error": "덤프를 찾을 수 없습니다: %s" % safe}
        try:
            d = D.Dump.load(src)
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        a = d.analyze()
        a["ok"] = True
        a["report"] = d.report()
        return a

    # -- 작업 시작 ---------------------------------------------------------

    def _start(self, kind: str, target: Callable[[Job], None]) -> dict[str, Any]:
        with self._lock:
            if self.job and self.job.running:
                return {"ok": False, "error": "이미 다른 작업이 진행 중입니다."}
            job = Job(kind)
            self.job = job

        def wrap() -> None:
            try:
                target(job)
            except Pm3Error as e:
                job.error = str(e)
                job.log("문제가 생겼습니다: %s" % e)
            except Exception as e:  # noqa: BLE001 - UI 로 전달하려고 폭넓게 잡는다
                job.error = "%s: %s" % (e.__class__.__name__, e)
                job.log("예상치 못한 오류: %s" % job.error)
            finally:
                # target 이 job.error 를 세웠으면(예: 복구 실패) 실패로 본다.
                job.ok = not job.error
                job.running = False

        threading.Thread(target=wrap, daemon=True).start()
        return {"ok": True}

    def start_auto(self) -> dict[str, Any]:
        def target(job: Job) -> None:
            res = workflow.one_touch(self.cfg, echo=job.log)
            if res.recovered and res.bin_path:
                job.result = {"bin": res.bin_path.name, "uid": res.info.uid}
            else:
                job.error = res.note or "덤프를 뜨지 못했습니다."

        return self._start("auto", target)

    def start_clone(self, name: str) -> dict[str, Any]:
        src = (self.cfg.out_path / name).resolve()
        # out 폴더 밖 경로로 빠져나가지 못하게 막는다.
        if self.cfg.out_path.resolve() not in src.parents or not src.is_file():
            return {"ok": False, "error": "그 덤프 파일을 찾을 수 없습니다: %s" % name}

        def target(job: Job) -> None:
            pm3 = Pm3.locate(self.cfg.pm3_path or None, self.cfg.port or None, self.cfg.out_path, deep=True)
            workflow.wait_for_device(pm3, self.cfg, job.log)
            workflow.clone_to_card(pm3, src, self.cfg, job.log)
            job.result = {"wrote": name}

        return self._start("clone", target)

    def start_update(self) -> dict[str, Any]:
        def target(job: Job) -> None:
            update.run(check_only=False, root=self.cfg.root, echo=job.log)

        return self._start("update", target)

    def start_setup(self) -> dict[str, Any]:
        from . import setup
        def target(job: Job) -> None:
            res = setup.bootstrap(self.cfg, echo=job.log, do_flash=None)
            self._dev_at = 0           # 상태 캐시 비우기
            if not res.get("ready"):
                job.error = "설정이 끝나지 않았습니다(클라이언트 없음 등)."

        return self._start("setup", target)

    def job_snapshot(self, since: int) -> dict[str, Any]:
        if self.job is None:
            return {"running": False, "idle": True, "total": 0, "lines": []}
        return self.job.snapshot(since)


def _make_handler(app: App):
    class Handler(BaseHTTPRequestHandler):
        server_version = "amsrfid/" + __version__

        def log_message(self, *a):  # 콘솔을 깨끗하게 — 접근 로그 끔
            pass

        def _send_json(self, obj: Any, code: int = 200) -> None:
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_html(self) -> None:
            try:
                body = UI_HTML.read_bytes()
            except OSError:
                body = b"<h1>ui.html not found</h1>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _body_json(self) -> dict[str, Any]:
            n = int(self.headers.get("Content-Length") or 0)
            if n <= 0:
                return {}
            try:
                return json.loads(self.rfile.read(n).decode("utf-8") or "{}")
            except (ValueError, UnicodeDecodeError):
                return {}

        def do_GET(self) -> None:
            path = self.path.split("?", 1)[0]
            if path in ("/", "/index.html"):
                return self._send_html()
            if path == "/api/status":
                return self._send_json(app.status())
            if path == "/api/dumps":
                return self._send_json(app.dumps())
            if path == "/api/analyze":
                q = self.path.split("?", 1)
                name = ""
                if len(q) == 2:
                    for kv in q[1].split("&"):
                        if kv.startswith("name="):
                            from urllib.parse import unquote
                            name = unquote(kv[5:])
                return self._send_json(app.analyze_dump(name))
            if path == "/api/job":
                q = self.path.split("?", 1)
                since = 0
                if len(q) == 2:
                    for kv in q[1].split("&"):
                        if kv.startswith("since="):
                            try:
                                since = int(kv[6:])
                            except ValueError:
                                since = 0
                return self._send_json(app.job_snapshot(since))
            return self._send_json({"error": "not found"}, 404)

        def do_POST(self) -> None:
            path = self.path.split("?", 1)[0]
            if path == "/api/auto":
                return self._send_json(app.start_auto())
            if path == "/api/update":
                return self._send_json(app.start_update())
            if path == "/api/driver":
                return self._send_json(app.install_driver())
            if path == "/api/setup":
                return self._send_json(app.start_setup())
            if path == "/api/clone":
                name = str(self._body_json().get("name") or "")
                return self._send_json(app.start_clone(name))
            if path == "/api/import":
                from urllib.parse import unquote
                n = int(self.headers.get("Content-Length") or 0)
                data = self.rfile.read(n) if n > 0 else b""
                name = ""
                q = self.path.split("?", 1)
                if len(q) == 2:
                    for kv in q[1].split("&"):
                        if kv.startswith("name="):
                            name = unquote(kv[5:])
                return self._send_json(app.import_bin(name, data))
            return self._send_json({"error": "not found"}, 404)

    return Handler


def serve(cfg: Config | None = None, host: str = "127.0.0.1", port: int = 8724,
          open_browser: bool = True, echo: Callable[[str], Any] = print) -> int:
    cfg = cfg or Config.load()
    app = App(cfg)
    httpd = ThreadingHTTPServer((host, port), _make_handler(app))
    url = "http://%s:%d/" % (host, httpd.server_address[1])
    echo("ams-rfid 웹 UI 가 열렸습니다: %s" % url)
    echo("(이 검은 창은 켜 두세요. 끄려면 Ctrl+C)")
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        echo("\n닫습니다.")
    finally:
        httpd.server_close()
    return 0
