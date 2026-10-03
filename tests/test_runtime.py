from __future__ import annotations

import hashlib
import io
from pathlib import Path

import pytest

from amsrfid import runtime
from amsrfid.pm3 import Pm3Error


def test_install_is_staged_and_reused(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "supported_platform", lambda: True)
    monkeypatch.setattr(runtime, "ensure_extractor", lambda echo: None)
    calls = []
    def download(path, echo):
        calls.append(path)
        path.write_bytes(b"archive")
    def extract(archive, dest):
        (dest / "client" / "libs").mkdir(parents=True)
        (dest / "client" / "proxmark3.exe").write_bytes(b"client")
    monkeypatch.setattr(runtime, "_download", download)
    monkeypatch.setattr(runtime, "_extract", extract)
    first = runtime.install(tmp_path, echo=lambda *a: None)
    assert Path(first).is_file()
    assert runtime.install(tmp_path, echo=lambda *a: None) == first
    assert len(calls) == 1
    assert not list((tmp_path / ".runtime").glob("install-*"))


def test_interrupted_install_does_not_mark_ready(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "supported_platform", lambda: True)
    monkeypatch.setattr(runtime, "ensure_extractor", lambda echo: None)
    def fail(path, echo):
        path.write_bytes(b"partial")
        raise OSError("network disconnected")
    monkeypatch.setattr(runtime, "_download", fail)
    with pytest.raises(Pm3Error, match="준비 실패"):
        runtime.install(tmp_path, echo=lambda *a: None)
    assert runtime.installed_client(tmp_path) is None
    assert not list((tmp_path / ".runtime").glob("install-*"))


def test_checksum_failure_stops_install(tmp_path, monkeypatch):
    class Response(io.BytesIO):
        headers = {"Content-Length": "7"}
    class Opener:
        def open(self, *a, **k):
            return Response(b"corrupt")
    monkeypatch.setattr(runtime, "_asset_request", lambda: object())
    monkeypatch.setattr(runtime.urllib.request, "build_opener", lambda *a: Opener())
    with pytest.raises(Pm3Error, match="검증 실패"):
        runtime._download(tmp_path / "download.7z", lambda *a: None)


def test_environment_uses_packaged_dlls_without_changing_parent(tmp_path, monkeypatch):
    (tmp_path / "libs").mkdir()
    monkeypatch.setenv("PATH", "original")
    monkeypatch.setenv("HOME", "original-home")
    env = runtime.client_environment(str(tmp_path / "proxmark3.exe"))
    assert str(tmp_path / "libs") in env["PATH"]
    assert env["HOME"] == "original-home"
    assert runtime.os.environ["PATH"] == "original"
