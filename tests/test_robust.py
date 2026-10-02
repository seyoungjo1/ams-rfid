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


def test_run_retries_once_on_disconnect(monkeypatch):
    p = pm3.Pm3(client="proxmark3", port="COM7")
    outs = [
        pm3.Pm3Result(0, "offline, cannot communicate with the proxmark", ""),
        pm3.Pm3Result(0, "os: ok\nUID: 11223344\n", ""),
    ]
    calls = {"n": 0}

    def fake_sub(args, timeout):
        i = calls["n"]
        calls["n"] += 1
        return outs[min(i, len(outs) - 1)]

    monkeypatch.setattr(p, "_run_subprocess", fake_sub)
    # replug 로 포트가 바뀐 상황: 재탐지하면 새 포트가 나온다
    monkeypatch.setattr(pm3, "detect_port", lambda: "COM8")
    res = p.run("hw version")
    assert calls["n"] == 2            # 끊김 신호 → 딱 한 번 재시도
    assert "os: ok" in res.text
    assert p.port == "COM8"           # 포트가 새로 갱신됨


def test_run_no_retry_when_fine(monkeypatch):
    p = pm3.Pm3(client="proxmark3", port="COM7")
    calls = {"n": 0}

    def fake_sub(args, timeout):
        calls["n"] += 1
        return pm3.Pm3Result(0, "[+] UID: DEADBEEF\n", "")

    monkeypatch.setattr(p, "_run_subprocess", fake_sub)
    p.run("hw version")
    assert calls["n"] == 1            # 정상 출력이면 재시도 없음
