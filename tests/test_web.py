from __future__ import annotations

import time
from pathlib import Path

from amsrfid import web
from amsrfid.config import Config


def _cfg(tmp_path: Path) -> Config:
    return Config(outdir=str(tmp_path / "out"), timeout=5, poll=0.01, wait=1, root=tmp_path)


def test_job_log_and_snapshot():
    j = web.Job("auto")
    j.log("첫 줄")
    j.log("둘\n셋")                 # 줄바꿈은 여러 줄로 쪼갠다
    snap = j.snapshot(0)
    assert snap["lines"] == ["첫 줄", "둘", "셋"]
    assert snap["total"] == 3
    assert j.snapshot(2)["lines"] == ["셋"]   # since 이후만


def test_dumps_lists_bins(tmp_path):
    cfg = _cfg(tmp_path)
    cfg.out_path.mkdir(parents=True)
    (cfg.out_path / "ams-DEAD.bin").write_bytes(b"\x00" * 1024)
    (cfg.out_path / "note.txt").write_text("x")
    app = web.App(cfg)
    names = [d["name"] for d in app.dumps()]
    assert names == ["ams-DEAD.bin"]
    assert app.dumps()[0]["size"] == 1024


def test_clone_rejects_missing_and_traversal(tmp_path):
    cfg = _cfg(tmp_path)
    cfg.out_path.mkdir(parents=True)
    app = web.App(cfg)
    assert app.start_clone("nope.bin")["ok"] is False
    # out 폴더 밖으로 빠져나가려는 경로는 막힌다
    assert app.start_clone("../../etc/passwd")["ok"] is False


def test_status_has_version(tmp_path):
    app = web.App(_cfg(tmp_path))
    s = app.status()
    assert "version" in s
    # pm3 가 깔려 있지 않은 CI 에서는 pm3=None 이어야 한다(예외가 아니라)
    assert "pm3" in s
    assert "port" in s          # 자동 탐지 포트 필드(없으면 None)


def test_import_bin_valid_and_invalid(tmp_path):
    app = web.App(_cfg(tmp_path))
    ok = app.import_bin("my dump.bin", b"\x00" * 1024)
    assert ok["ok"] is True
    assert ok["name"].endswith(".bin")
    assert (app.cfg.out_path / ok["name"]).is_file()
    bad = app.import_bin("x.bin", b"\x00" * 100)
    assert bad["ok"] is False


def test_analyze_dump_reports(tmp_path):
    from amsrfid import dump as D
    app = web.App(_cfg(tmp_path))
    d = D.Dump()
    d.data[0:4] = bytes.fromhex("3359C8E4")
    d.data[60 * 16 : 60 * 16 + 16] = bytes.fromhex("600907924052340020201620202020CC")
    tb = D.trailer_block(15) * 16
    d.data[tb : tb + 6] = bytes.fromhex("23C7F6BAE3EB")
    d.data[tb + 10 : tb + 16] = bytes.fromhex("23C7F6BAE3EB")
    app.import_bin("real.bin", bytes(d.data))
    a = app.analyze_dump("real.bin")
    assert a["ok"] is True
    assert a["custom_sectors"] == 1
    assert "report" in a
    miss = app.analyze_dump("nope.bin")
    assert miss["ok"] is False


def test_detect_port_no_crash():
    from amsrfid import pm3
    # 하드웨어가 없어도 예외 없이 None/str 을 돌려줘야 한다
    p = pm3.detect_port()
    assert p is None or isinstance(p, str)


def test_detect_device_shape():
    from amsrfid import pm3
    dev = pm3.detect_device()
    for k in ("present", "com", "needs_driver"):
        assert k in dev


def test_pm3_match_vidpid():
    from amsrfid import pm3
    assert pm3._pm3_match(r"USB\VID_502D&PID_502D\5&abc")      # Proxmark3 Easy
    assert pm3._pm3_match(r"USB\VID_9AC4&PID_4B8F\6")          # 정품
    assert pm3._pm3_match(r"usb\vid_2d2d&pid_504d\x")          # 소문자도
    assert not pm3._pm3_match(r"USB\VID_1234&PID_5678\x")      # 무관한 장치
    assert pm3._com_of("Proxmark3 (easy?) (COM7)") == "COM7"
    assert pm3._com_of("something no com") is None


def test_pyserial_detection(monkeypatch):
    from amsrfid import pm3
    # pyserial 이 PM3 Easy(VID 0x502D/PID 0x502D) 포트를 보고하면 바로 잡아야 한다
    monkeypatch.setattr(pm3, "_pyserial_ports", lambda: [
        {"device": "COM1", "vid": 0x1234, "pid": 0x5678, "desc": "random"},
        {"device": "COM7", "vid": 0x502D, "pid": 0x502D, "desc": "USB Serial Device"},
    ])
    dev = pm3.detect_device()
    assert dev["present"] is True and dev["com"] == "COM7"


def test_pyserial_detection_by_description(monkeypatch):
    from amsrfid import pm3
    # VID/PID 가 없어도 설명에 proxmark 가 있으면 잡는다(GUI 와 같은 fallback)
    monkeypatch.setattr(pm3, "_pyserial_ports", lambda: [
        {"device": "/dev/ttyACM0", "vid": None, "pid": None, "desc": "Proxmark3 Iceman"},
    ])
    assert pm3.detect_port() == "/dev/ttyACM0"


def test_diagnostics_shape():
    from amsrfid import pm3
    d = pm3.diagnostics()
    for k in ("os", "com_ports", "pm3_devices", "device", "client"):
        assert k in d
    assert isinstance(d["com_ports"], list)


def test_install_driver_returns_tuple():
    from amsrfid import pm3
    ok, msg = pm3.install_driver()
    assert isinstance(ok, bool) and isinstance(msg, str)
    # 번들된 공식 inf 가 저장소에 있어야 한다
    assert pm3.default_inf().name == "proxmark3.inf"


def test_status_exposes_device_fields(tmp_path):
    app = web.App(_cfg(tmp_path))
    s = app.status()
    for k in ("device_present", "needs_driver", "port"):
        assert k in s


def test_update_job_runs_in_thread(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    app = web.App(cfg)

    def fake_update_run(check_only=False, root=None, echo=print):
        echo("업데이트 확인 중…")
        echo("최신입니다.")
        return 0

    monkeypatch.setattr(web.update, "run", fake_update_run)
    assert app.start_update()["ok"] is True
    # 스레드가 끝날 때까지 잠깐 기다린다
    for _ in range(100):
        if app.job and not app.job.running:
            break
        time.sleep(0.01)
    snap = app.job_snapshot(0)
    assert snap["running"] is False
    assert snap["ok"] is True
    assert "최신입니다." in snap["lines"]


def test_only_one_job_at_a_time(tmp_path, monkeypatch):
    app = web.App(_cfg(tmp_path))

    def slow(check_only=False, root=None, echo=print):
        time.sleep(0.2)

    monkeypatch.setattr(web.update, "run", slow)
    assert app.start_update()["ok"] is True
    second = app.start_update()        # 아직 도는 중 — 거절돼야 한다
    assert second["ok"] is False


def test_status_never_enumerates_devices(tmp_path, monkeypatch):
    from amsrfid import pm3
    def forbidden(*args, **kwargs):
        raise AssertionError("background device enumeration")
    monkeypatch.setattr(pm3, "detect_device", forbidden)
    monkeypatch.setattr(pm3, "_pyserial_ports", forbidden)
    monkeypatch.setattr(pm3, "_win_scan", forbidden)
    app = web.App(_cfg(tmp_path))
    assert app.status()["device_checked"] is False
    app._dev = {"present": True, "com": "COM7"}
    assert app.status()["port"] == "COM7"
