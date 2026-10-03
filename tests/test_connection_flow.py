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
    return Config(pm3_path=str(client), port="COM_TEST", root=tmp_path,
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
