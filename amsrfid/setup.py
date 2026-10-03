"""클라이언트를 찾고 상태를 확인한다(안전한 얇은 래퍼).

Proxmark3GUI 처럼 **시스템을 건드리지 않는다** — 드라이버 자동설치(pnputil)·자동 펌웨어
플래싱은 과거 시스템 오류(fault)를 일으켜 전부 제거했다. 여기서는 pyserial 로 포트를 보고,
클라이언트를 찾고, 상태만 알려 준다. 드라이버·펌웨어는 사람이 직접(안내대로) 한다.
"""
from __future__ import annotations

import re
from typing import Any, Callable

from . import pm3 as P
from .config import Config

Echo = Callable[[str], Any]


def ensure_driver(echo: Echo = print) -> dict:
    """드라이버는 **설치하지 않는다** — 상태만 알려 주고, 장치 정보를 돌려준다(한 번만 열거)."""
    dev = P.detect_device()
    if dev.get("com"):
        echo("· 장치 OK — 포트 %s" % dev.get("com"))
    elif dev.get("present"):
        echo("· 장치는 보이는데 COM 포트가 없습니다. 보통 '충전 전용 USB 케이블'이 원인입니다 —")
        echo("  데이터선 있는 케이블 + 본체 USB 포트로 바꿔 꽂아 보세요.(드라이버 자동설치는 안 합니다)")
    else:
        echo("· 아직 장치가 안 보입니다 — USB 에 꽂아 주세요(데이터선 케이블).")
    return dev


def ensure_client(cfg: Config, echo: Echo = print, deep: bool = False) -> str | None:
    try:
        c = P.find_client(cfg.pm3_path or None)
        echo("· 클라이언트 OK: %s" % c)
        return c
    except P.DeviceNotFound:
        pass
    if deep:
        echo("· 알려진 설치 폴더에서 클라이언트를 찾는 중…")
        found = P.deep_find_client()
        if found:
            echo("  → 찾음: %s  (pm3_path.txt 에 저장)" % found)
            return found
    echo("· Proxmark3 클라이언트(proxmark3.exe)를 찾지 못했습니다.")
    echo("  원터치 시작/연결 확인에서 Easy용 클라이언트를 자동 준비합니다.")
    return None


def prepare_device(cfg: Config, echo: Echo = print) -> P.Pm3:
    """User-started preparation: install missing client, find port, verify version."""
    from . import runtime, workflow
    if runtime.supported_platform() and not cfg.use_system_client:
        # Fresh portable install is the Windows default, even if an old config/PATH exists.
        client = runtime.install(cfg.root, echo)
        port = None
    else:
        client = runtime.installed_client(cfg.root) if not cfg.pm3_path else None
        if not client:
            client = ensure_client(cfg, echo, deep=False)
        if not client:
            client = runtime.install(cfg.root, echo)
        port = cfg.port or None
    cfg.pm3_path = client
    pm3 = P.Pm3(client=client, port=port, workdir=cfg.out_path, echo=echo)
    if runtime.supported_platform() and not cfg.use_system_client:
        # The managed build supports this flag: ignore old ~/.proxmark3 preferences.
        pm3.extra_args.append("--incognito")
    workflow.wait_for_device(pm3, cfg, echo)
    version = pm3.run("hw version", timeout=30).text
    if not re.search(r"(?:\bos:|\bOS\.+)\s*\S", version, re.I):
        raise P.Pm3Error("장치의 펌웨어 응답을 확인하지 못했습니다. 연결 로그를 확인하세요.")
    if "does not match" in version.lower() or "mismatch" in version.lower():
        raise P.Pm3Error("클라이언트와 장치 펌웨어 버전이 다릅니다. 카드 작업을 중단했습니다. Easy의 메모리 용량에 맞는 펌웨어 준비가 필요합니다.")
    echo("연결 완료 · " + str(pm3.port))
    return pm3


def flash_if_needed(cfg: Config, client: str, echo: Echo = print, force: bool = False) -> bool:
    """펌웨어 플래싱 — **명시적으로 요청할 때만**(`amsrfid flash`). 자동 호출하지 않는다."""
    pm3 = P.Pm3(client=client, port=cfg.port or None, workdir=cfg.out_path)
    if not pm3.device_present():
        echo("· 장치가 응답하지 않습니다(꽂힘/케이블 확인). 플래싱을 멈춥니다.")
        return False
    imgs = P.find_firmware_images(client)
    if not imgs.get("fullimage"):
        echo("· fullimage.elf 를 못 찾았습니다. pm3 셸에서 `pm3-flash-all` 로 올리세요.")
        return False
    echo("· 펌웨어를 플래싱합니다(fullimage) — 장치를 뽑지 마세요…")
    res = pm3.run_raw(["--flash", "--image", imgs["fullimage"]], timeout=max(cfg.timeout, 300))
    low = res.text.lower()
    # pm3 의 한방 종료코드는 서브명령마다 믿을 게 못 되므로, 완료 배너로도 확인한다.
    ok = (("have a nice day" in low) or ("done" in low) or ("wrote" in low) or ("success" in low)) \
        and "fail" not in low and "error" not in low
    if not ok:
        echo("  → 플래싱이 안 끝났을 수 있습니다. 부트로더 모드(버튼 누른 채 꽂기)가 필요할 수 있어요.")
        echo(res.text[-400:])
        return False
    echo("  → 플래싱 완료. 장치가 재부팅됩니다.")
    return True


def bootstrap(cfg: Config, echo: Echo = print, do_flash: bool | None = None) -> dict:
    """상태 점검만: 클라이언트 찾기 + 장치/포트 확인. **드라이버 설치·펌웨어 플래싱 안 함.**

    do_flash 는 호환용으로 받지만 무시한다(자동 플래싱 제거).
    """
    echo("=== 상태 확인 ===")
    if cfg.port:
        dev = {"present": False, "com": cfg.port}
        echo("· 지정된 포트 %s 사용 (통신은 읽기 실행 시 확인)" % cfg.port)
    else:
        dev = ensure_driver(echo)             # 장치 열거는 여기서 한 번만
    client = ensure_client(cfg, echo, deep=True)
    result = {
        "client": client,
        "flashed": False,
        "device_present": dev.get("present", False),
        "port": dev.get("com"),
        "ready": bool(client and dev.get("com")),
    }
    if client and dev.get("com"):
        echo("=== 경로·포트 확인됨 — '원터치 읽기'를 누르면 카드를 읽습니다 ===")
    elif client:
        echo("=== 클라이언트는 있는데 장치 포트가 안 잡힙니다(케이블/포트 확인) ===")
    else:
        echo("=== 클라이언트가 없습니다(위 안내 참고) ===")
    return result


def check_connection(cfg: Config, echo: Echo = print) -> dict:
    pm3 = prepare_device(cfg, echo)
    return {"client": pm3.client, "port": pm3.port, "connected": True,
            "ready": True, "device_present": True, "flashed": False}
