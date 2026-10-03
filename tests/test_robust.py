from __future__ import annotations

from amsrfid import pm3


def test_ansi_strip_in_text():
    r = pm3.Pm3Result(0, "\x1b[32m[+] UID: DEAD\x1b[0m\n", "")
    assert "\x1b[" not in r.text
    assert "[+] UID: DEAD" in r.text


def test_looks_disconnected():
    assert pm3._looks_disconnected("offline mode, cannot communicate with the Proxmark3")
    assert pm3._looks_disconnected("Failed to open serial port")
    assert not pm3._looks_disconnected("[+] UID: DEADBEEF  os: ok")


def test_port_is_pm3_by_manufacturer():
    assert pm3._port_is_pm3({"vid": None, "pid": None, "desc": "USB Serial Device",
                             "manufacturer": "proxmark.org"})
    assert pm3._port_is_pm3({"vid": 0x9AC4, "pid": 0x4B8F, "desc": "x", "manufacturer": ""})
    assert not pm3._port_is_pm3({"vid": 0x1234, "pid": 0x5678, "desc": "random", "manufacturer": "acme"})


def test_run_does_not_replay_on_disconnect(monkeypatch):
    p = pm3.Pm3(client="proxmark3", port="COM7")
    calls = []
    def fake_sub(args, timeout):
        calls.append(args)
        return pm3.Pm3Result(1, "offline, cannot communicate with the proxmark", "")
    monkeypatch.setattr(p, "_run_subprocess", fake_sub)
    monkeypatch.setattr(pm3, "detect_port", lambda: "COM8")
    import pytest
    with pytest.raises(pm3.Pm3Error, match="offline"):
        p.run("hf mf cload -f backup.bin")
    assert len(calls) == 1
    assert p.port == "COM7"


def test_run_no_retry_when_fine(monkeypatch):
    p = pm3.Pm3(client="proxmark3", port="COM7")
    calls = {"n": 0}

    def fake_sub(args, timeout):
        calls["n"] += 1
        return pm3.Pm3Result(0, "[+] UID: DEADBEEF\n", "")

    monkeypatch.setattr(p, "_run_subprocess", fake_sub)
    p.run("hw version")
    assert calls["n"] == 1            # 정상 출력이면 재시도 없음


def test_no_port_does_not_launch_wrapper(monkeypatch):
    import pytest
    p = pm3.Pm3(client="pm3")
    monkeypatch.setattr(pm3, "detect_port", lambda: None)
    monkeypatch.setattr(p, "_run_subprocess", lambda *a: pytest.fail("wrapper launched"))
    with pytest.raises(pm3.DeviceNotFound):
        p.run("hw version")


def test_explicit_path_skips_search(tmp_path, monkeypatch):
    client = tmp_path / "proxmark3.exe"
    client.touch()
    def forbidden(*args, **kwargs):
        raise AssertionError("installation search with explicit path")
    monkeypatch.setattr(pm3.shutil, "which", forbidden)
    monkeypatch.setattr(pm3.glob, "glob", forbidden)
    assert pm3.find_client(str(client)) == str(client)


def test_card_wait_propagates_connection_errors(monkeypatch):
    import pytest
    p = pm3.Pm3(client="proxmark3", port="COM7")
    monkeypatch.setattr(p, "_run_subprocess", lambda *a: pm3.Pm3Result(1, "port unavailable", ""))
    with pytest.raises(pm3.Pm3Error, match="port unavailable"):
        p.card_present()


def test_successful_serial_banner_is_not_a_disconnect(monkeypatch):
    p = pm3.Pm3(client="proxmark3", port="COM7")
    monkeypatch.setattr(p, "_run_subprocess", lambda *a: pm3.Pm3Result(0, "Using serial port COM7\nUID: DEADBEEF\nATQA: 00 04", ""))
    assert p.card_present()


def test_identify_uses_one_command_argument():
    args = pm3.Pm3(client="proxmark3", port="COM7")._build_args(["hf 14a info", "hf mf info"])
    assert args.count("-c") == 1
    assert args[-1] == "hf 14a info; hf mf info"
