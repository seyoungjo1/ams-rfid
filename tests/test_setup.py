from __future__ import annotations

from pathlib import Path

from amsrfid import setup, pm3 as P
from amsrfid.config import Config


def _cfg(tmp_path: Path) -> Config:
    return Config(outdir=str(tmp_path / "out"), timeout=5, poll=0.01, wait=1, root=tmp_path)


def test_bootstrap_no_client_stops(tmp_path, monkeypatch):
    # 클라이언트를 못 찾는 상황: 깊은 탐색도 None
    monkeypatch.setattr(P, "detect_device", lambda: {"present": False, "com": None, "needs_driver": False})
    monkeypatch.setattr(P, "find_client", lambda *a, **k: (_ for _ in ()).throw(P.DeviceNotFound("x")))
    monkeypatch.setattr(P, "deep_find_client", lambda *a, **k: None)
    res = setup.bootstrap(_cfg(tmp_path), echo=lambda *a: None, do_flash=False)
    assert res["ready"] is False
    assert res["client"] is None


def test_bootstrap_with_client_ready(tmp_path, monkeypatch):
    fake = str(tmp_path / "proxmark3")
    Path(fake).write_text("#!stub")
    monkeypatch.setattr(P, "detect_device", lambda: {"present": True, "com": "COM3", "needs_driver": False})
    monkeypatch.setattr(P, "find_client", lambda *a, **k: fake)
    res = setup.bootstrap(_cfg(tmp_path), echo=lambda *a: None, do_flash=False)
    assert res["ready"] is True
    assert res["client"] == fake


def test_ensure_driver_never_autoinstalls(tmp_path, monkeypatch):
    # 안전: ensure_driver 는 어떤 경우에도 install_driver 를 자동 호출하지 않는다(상태만 보고).
    called = {}
    monkeypatch.setattr(P, "detect_device", lambda: {"present": True, "com": None, "needs_driver": True})

    def boom(*a, **k):
        called["yes"] = True
        return (True, "설치됨")

    monkeypatch.setattr(P, "install_driver", boom)
    assert isinstance(setup.ensure_driver(echo=lambda *a: None), dict)
    assert "yes" not in called          # 절대 자동 설치하지 않음


def test_find_firmware_images_shape(tmp_path):
    # 클라이언트 근처에 가짜 이미지
    cdir = tmp_path / "pm3" / "client"
    cdir.mkdir(parents=True)
    client = cdir / "proxmark3"
    client.write_text("stub")
    (tmp_path / "pm3" / "armsrc" / "obj").mkdir(parents=True)
    (tmp_path / "pm3" / "armsrc" / "obj" / "fullimage.elf").write_text("elf")
    imgs = P.find_firmware_images(str(client))
    assert imgs["fullimage"] and imgs["fullimage"].endswith("fullimage.elf")


def test_deep_find_client_no_crash(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "_scan_roots", lambda: [tmp_path])
    # pm3 실행 파일 하나 심어 두면 찾아야 한다
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "proxmark3").write_text("stub")
    monkeypatch.setattr(P, "_root", lambda: tmp_path)   # pm3_path.txt 쓰기 대상
    found = P.deep_find_client()
    assert found and found.endswith("proxmark3")


def test_configured_port_skips_enumeration(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    cfg.port = "COM7"
    monkeypatch.setattr(P, "find_client", lambda *a, **k: "proxmark3.exe")
    def forbidden():
        raise AssertionError("explicit port must bypass enumeration")
    monkeypatch.setattr(P, "detect_device", forbidden)
    assert setup.bootstrap(cfg, echo=lambda *a: None)["port"] == "COM7"
