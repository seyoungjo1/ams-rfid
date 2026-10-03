"""Exercise the actual process and HTTP boundary, including Windows .cmd launch."""
from __future__ import annotations

import json
import os
import shutil
import sys
import threading
import time
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from amsrfid import cli, menu, web, workflow
from amsrfid.config import Config
from amsrfid.pm3 import Pm3, Pm3Error


@pytest.fixture
def connected_config(tmp_path):
    folder = tmp_path / "client with spaces"
    folder.mkdir()
    script = folder / "stub.py"
    shutil.copyfile(Path(__file__).parent / "stub" / "proxmark3_stub.py", script)
    if os.name == "nt":
        client = folder / "pm3.cmd"
        client.write_text('@echo off\n"%s" "%s" %%*\n' % (sys.executable, script))
    else:
        client = script
        client.chmod(0o755)
    return Config(use_system_client=True, pm3_path=str(client), port="COM_TEST", root=tmp_path,
                  outdir="new output", timeout=30, poll=0.01, wait=1)


def test_cli_connect_and_first_read(connected_config, monkeypatch):
    cfg = connected_config
    monkeypatch.setattr(cli.Config, "load", lambda: cfg)
    assert cli.main(["connect"]) == 0
    assert not list(cfg.out_path.glob("*.bin"))
    assert cli.main(["auto"]) == 0
    assert list(cfg.out_path.glob("ams-DEADBEEF-*.bin"))


def test_http_connection_job(connected_config):
    app = web.App(connected_config)
    server = ThreadingHTTPServer(("127.0.0.1", 0), web._make_handler(app))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = "http://127.0.0.1:%d" % server.server_address[1]
    def get(path):
        with urllib.request.urlopen(base + path, timeout=5) as response:
            return json.load(response)
    try:
        assert not get("/api/status")["connected"]
        with urllib.request.urlopen(urllib.request.Request(base + "/api/connect", method="POST"), timeout=5) as response:
            assert json.load(response)["ok"]
        deadline = time.monotonic() + 10
        while True:
            job = get("/api/job")
            if not job["running"]:
                break
            assert time.monotonic() < deadline
            time.sleep(0.02)
        assert job["ok"], job
        assert get("/api/status")["connected"]
        assert job["result"]["port"] == "COM_TEST"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_missing_executable_stops_before_card_poll(connected_config):
    cfg = connected_config
    pm3 = Pm3(client=str(cfg.root / "missing.exe"), port=cfg.port, workdir=cfg.out_path)
    with pytest.raises(Pm3Error, match="pm3"):
        workflow.wait_for_card(pm3, cfg, echo=lambda *a: None)


def test_menu_read_action_has_workflow_binding(connected_config, monkeypatch):
    choices = iter(["1", "0"])
    monkeypatch.setattr("builtins.input", lambda *a: next(choices))
    assert menu.run(connected_config) == 0
    assert list(connected_config.out_path.glob("ams-DEADBEEF-*.bin"))


def wait_job(app):
    deadline = time.monotonic() + 10
    while app.job and app.job.running:
        assert time.monotonic() < deadline
        time.sleep(0.01)
    return app.job_snapshot(0)


def test_wizard_waits_for_swap_then_writes(connected_config):
    app = web.App(connected_config)
    assert app.write_pending(True)["ok"] is False
    assert app.start_wizard()["ok"]
    read = wait_job(app)
    assert read["ok"], read
    assert read["phase"] == "awaiting_target"
    assert app.pending_write
    assert not any(line.startswith("▶") and "cload" in line for line in read["lines"])
    assert not app.write_pending(False)["ok"]
    assert app.write_pending(True)["ok"]
    write = wait_job(app)
    assert write["ok"], write
    assert write["result"]["verified"] is True
    assert app.pending_write is None
    assert app.write_pending(True)["ok"] is False


def test_wizard_rejects_changed_source(connected_config):
    app = web.App(connected_config)
    app.start_wizard()
    assert wait_job(app)["ok"]
    (connected_config.out_path / app.pending_write["name"]).write_bytes(b"changed")
    app.write_pending(True)
    result = wait_job(app)
    assert not result["ok"]
    assert "변경" in result["error"]


def test_pm3_streams_before_process_exit(tmp_path):
    from threading import Event
    seen = Event()
    finished = tmp_path / "finished"
    def log(line):
        if "first-line" == line:
            assert not finished.exists()
            seen.set()
    pm3 = Pm3(client=sys.executable, workdir=tmp_path, echo=log)
    script = "import time,pathlib; print('first-line',flush=True); time.sleep(.3); pathlib.Path('finished').touch()"
    result = pm3._run_subprocess([sys.executable, "-u", "-c", script], 5)
    assert result.returncode == 0 and seen.is_set()
    assert finished.exists()


def test_pm3_timeout_keeps_partial_output(tmp_path):
    pm3 = Pm3(client=sys.executable, workdir=tmp_path)
    script = "import time; print('still-working',flush=True); time.sleep(10)"
    with pytest.raises(Pm3Error, match="시간 제한"):
        pm3._run_subprocess([sys.executable, "-u", "-c", script], 0.5)
    assert "still-working" in (tmp_path / "last-pm3.log").read_text(encoding="utf-8")


def test_missing_pm3_is_installed_before_read(connected_config, monkeypatch):
    from amsrfid import setup, runtime
    cfg = connected_config
    stub = cfg.pm3_path
    cfg.pm3_path = ""
    installed = []
    monkeypatch.setattr(setup, "ensure_client", lambda *a, **k: None)
    monkeypatch.setattr(runtime, "installed_client", lambda *a: None)
    def install(root, echo):
        installed.append(root)
        return stub
    monkeypatch.setattr(runtime, "install", install)
    result = workflow.one_touch(cfg, echo=lambda *a: None)
    assert result.recovered and installed == [cfg.root]
    assert cfg.pm3_path == stub
