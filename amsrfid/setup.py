"""딸깍 한 번에: 드라이버 → 클라이언트 → (필요하면) 펌웨어 → 준비 완료.

공식 Proxmark3 도구를 엮기만 한다. 이미 있는 건 그대로 쓰고, 없는 것만 설치하거나 안내한다.
  1) 드라이버  : 공식 proxmark3.inf 를 pnputil 로 설치(장치는 보이는데 COM 이 없을 때).
  2) 클라이언트: proxmark3.exe/pm3 를 흔한 위치 → 드라이브 깊은 탐색으로 찾는다.
  3) 펌웨어    : FM11RF08S 백도어를 지원 안 하면 fullimage 를 플래싱(공식 --flash).
이 과정을 run.bat/웹UI 의 '전체 설정'과 원터치 읽기가 앞단에서 부른다.
"""
from __future__ import annotations

from typing import Any, Callable

from . import pm3 as P
from .config import Config

Echo = Callable[[str], Any]


def ensure_driver(echo: Echo = print) -> bool:
    dev = P.detect_device()
    if dev.get("needs_driver"):
        echo("· 드라이버가 없어 COM 포트가 안 잡힙니다 — 공식 드라이버를 설치합니다(관리자 UAC)…")
        ok, msg = P.install_driver()
        echo("  → " + msg)
        return ok
    if dev.get("present"):
        echo("· 드라이버 OK (장치 감지됨%s)" % (" " + dev.get("com") if dev.get("com") else ""))
    else:
        echo("· 아직 장치가 안 보입니다 — USB 에 꽂아 주세요(드라이버는 꽂은 뒤 설치합니다).")
    return True


def ensure_client(cfg: Config, echo: Echo = print) -> str | None:
    try:
        c = P.find_client(cfg.pm3_path or None)
        echo("· 클라이언트 OK: %s" % c)
        return c
    except P.DeviceNotFound:
        pass
    echo("· 클라이언트를 드라이브에서 찾는 중… (처음 한 번만, 조금 걸립니다)")
    found = P.deep_find_client()
    if found:
        echo("  → 찾음: %s  (pm3_path.txt 에 저장해 다음부턴 바로 씀)" % found)
        return found
    echo("· Proxmark3 클라이언트(proxmark3.exe)를 찾지 못했습니다.")
    echo("  ProxSpace 또는 https://www.proxmarkbuilds.org 로 설치한 뒤,")
    echo("  이 폴더의 pm3_path.txt 에 proxmark3.exe 경로를 한 줄 적어 주세요.")
    return None


def flash_if_needed(cfg: Config, client: str, echo: Echo = print, force: bool = False) -> bool:
    """FM11RF08S 백도어 미지원 펌웨어면 fullimage 를 플래싱한다(버튼 없이 되는 범위)."""
    pm3 = P.Pm3(client=client, port=cfg.port or None, workdir=cfg.out_path)
    if not pm3.device_present():
        echo("· 장치가 응답하지 않아 펌웨어 확인은 건너뜁니다(꽂힘/드라이버 확인).")
        return True
    if not force and pm3.supports_fm11rf08s():
        echo("· 펌웨어 OK — FM11RF08S 백도어 지원.")
        return True
    imgs = P.find_firmware_images(client)
    if not imgs.get("fullimage"):
        echo("· 펌웨어 업데이트가 필요해 보이는데 fullimage.elf 를 못 찾았습니다.")
        echo("  pm3 셸에서 `pm3-flash-all` 로 최신 Iceman 을 올리면 백도어가 됩니다.")
        return False
    echo("· 펌웨어를 최신으로 플래싱합니다(fullimage) — 수십 초, 장치를 뽑지 마세요…")
    res = pm3.run_raw(["--flash", "--image", imgs["fullimage"]], timeout=max(cfg.timeout, 300))
    low = res.text.lower()
    ok = res.returncode == 0 and ("done" in low or "wrote" in low or "success" in low) and "fail" not in low
    if not ok:
        echo("  → 플래싱이 안 끝났을 수 있습니다. 부트로더 모드(버튼 누른 채 꽂기)가 필요할 수 있어요.")
        echo(res.text[-400:])
        return False
    echo("  → 플래싱 완료. 장치가 재부팅됩니다.")
    return True


def bootstrap(cfg: Config, echo: Echo = print, do_flash: bool | None = None) -> dict:
    """드라이버 → 클라이언트 → (필요시)펌웨어. 준비 상태를 돌려준다.

    do_flash: None=필요할 때만, True=무조건, False=건너뜀.
    """
    echo("=== 전체 설정 시작 ===")
    ensure_driver(echo)
    client = ensure_client(cfg, echo)
    result = {"client": client, "flashed": False, "ready": False}
    if not client:
        echo("=== 클라이언트가 없어 여기서 멈춥니다 ===")
        return result
    if do_flash is not False:
        result["flashed"] = flash_if_needed(cfg, client, echo, force=bool(do_flash))
    pm3 = P.Pm3(client=client, port=cfg.port or None, workdir=cfg.out_path)
    dev = P.detect_device()
    result["device_present"] = dev.get("present", False)
    result["port"] = dev.get("com")
    result["ready"] = bool(client)
    echo("=== 설정 완료 — 이제 '원터치 읽기'를 누르면 카드를 읽습니다 ===")
    return result
