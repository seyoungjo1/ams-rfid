"""Explicit Easy firmware recovery using the pinned client's legacy flasher.

The no-image --flash command enters/restarts the bootloader and reports memory,
but writes no image. See RRG client/src/proxmark3.c: flash_pm3 and flash.c.
Never require an NG capabilities handshake before recovery, and never --force.
"""
from __future__ import annotations

import hashlib
import re
import time
from pathlib import Path

from . import runtime
from .config import Config
from .pm3 import Pm3, Pm3Error, Pm3Result, _pyserial_ports, _port_is_pm3

IMAGE_HASHES = {
    "bootrom": "d2d7f97e8b9daf07aa6901951a153a4f1debc9591d77fe76860cbd5d0c34e2c6",
    "fullimage": "3d4cc8f0afc56bebee1e1e464b3aa39e8f5c306c02eae966679904d72085f119",
}
SOURCE_REVISION = "da50946"
BUTTON_GUIDE = (
    "부트로더 연결에 실패하면 USB를 뽑고 Easy 버튼을 누른 채 다시 연결하세요. "
    "두 LED가 유지되면 버튼을 놓으세요. 놓을 때 LED가 꺼지는 구형 장치는 쓰기 동안 누르고 있어야 합니다. "
    "복구가 끝나면 버튼을 놓고 USB를 다시 연결한 뒤 연결 확인을 실행하세요."
)


def verified_images(client: str) -> dict[str, Path]:
    """Only the exact generic images extracted from our checksum-pinned archive."""
    images = {}
    for name, digest in IMAGE_HASHES.items():
        path = Path(client).parent / (name + ".elf")
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise Pm3Error("동일 배포본의 %s.elf 검증에 실패했습니다. 펌웨어를 쓰지 않았습니다." % name)
        images[name] = path.resolve()
    return images


def wait_port(timeout: float, echo, *, settle: bool = False, serial: str = "") -> dict:
    # Flashing resets USB. Enumerate again rather than assuming the old COM number.
    if settle:
        time.sleep(2)
    deadline = time.monotonic() + timeout
    while True:
        ports = [p for p in (_pyserial_ports() or []) if _port_is_pm3(p)]
        if len(ports) > 1:
            raise Pm3Error("Proxmark3가 여러 대 연결되어 있습니다. 복구할 Easy 한 대만 연결하세요.")
        if ports:
            device = ports[0]
            if serial and device.get("serial") and device["serial"] != serial:
                raise Pm3Error("재연결된 장치의 일련번호가 달라 복구를 중단했습니다.")
            echo("복구 포트: " + device["device"])
            return device
        if time.monotonic() >= deadline:
            raise Pm3Error("복구할 Easy의 COM 포트를 찾지 못했습니다. " + BUTTON_GUIDE)
        time.sleep(0.5)


def check_flash_result(result: Pm3Result, *, image: bool) -> str:
    text = result.text
    low = text.lower()
    # RRG can replace a flash failure's exit code with flash_stop_flashing's 0,
    # then print 'All done'/'Have a nice day'. Those banners alone are insufficient.
    failed = re.search(r"\berror\b|\bfailed\b|\baborted\b|\bcould not\b|\bcouldn't\b|\btimeout\b|\btimed out\b", low)
    success = "all done" in low
    if image:
        success = success and "flashing..." in low and "writing segments for file:" in low
    else:
        success = success and "available memory on this board:" in low
    if result.returncode != 0 or failed or not success:
        raise Pm3Error("펌웨어 작업을 완료하지 못했습니다. 자동 재시도하지 않습니다.\n" + BUTTON_GUIDE + "\n" + text[-3000:])
    return text


def memory_kb(text: str) -> int | None:
    match = re.search(r"Available memory on this board:\s*(\d+)K\s+bytes", text, re.I)
    return int(match.group(1)) if match else None


def repair(cfg: Config, echo=print, stage=lambda phase: None, *, confirmed: bool = False) -> dict:
    if not confirmed:
        raise Pm3Error("Easy의 부트로더와 펌웨어 변경 확인이 필요합니다.")
    lines = []
    def log(message):
        lines.append(str(message))
        echo(message)
    try:
        stage("firmware_check")
        log("Easy 펌웨어 복구 · " + runtime.BUILD)
        log("부트로더와 펌웨어를 변경합니다. 완료할 때까지 USB와 전원을 유지하세요.")
        client = runtime.install(cfg.root, log)
        images = verified_images(client)
        device = wait_port(min(cfg.wait, 60), log)
        identity = device.get("serial", "")
        pm3 = Pm3(client=client, port=device["device"], workdir=cfg.out_path,
                  extra_args=["--incognito", "-f"], echo=log)

        def rediscover():
            pm3.port = wait_port(min(cfg.wait, 60), log, settle=True, serial=identity)["device"]

        def inspect():
            log("부트로더·용량 확인 (이미지 쓰기 없음, 장치가 재시작됩니다)")
            result = pm3.run_raw(["--flash"], timeout=120)
            return memory_kb(check_flash_result(result, image=False))

        size = inspect()
        if size is not None and size != 512:
            raise Pm3Error("장치 용량 %sKB: 동봉된 Easy 펌웨어는 512KB용입니다. 아무 이미지도 쓰지 않았습니다. 256KB 장치는 별도 축소 빌드가 필요합니다." % size)
        if size is None:
            log("구형 부트로더가 용량을 보고하지 않습니다. 공용 부트로더만 먼저 갱신하고 용량을 다시 확인합니다.")
        rediscover()
        stage("firmware_bootrom")
        log("1/2 부트로더 갱신")
        check_flash_result(pm3.run_raw(["--flash", "--unlock-bootloader", "--image", str(images["bootrom"])], timeout=300), image=True)
        rediscover()
        size = inspect()
        if size != 512:
            raise Pm3Error("부트로더 갱신 후 용량 %s: 512KB를 확인하지 못해 본 펌웨어는 쓰지 않았습니다. 256KB라면 별도 축소 빌드가 필요합니다." % (str(size) + "KB" if size else "알 수 없음"))
        rediscover()
        stage("firmware_image")
        log("2/2 Easy 512KB 펌웨어 갱신")
        check_flash_result(pm3.run_raw(["--flash", "--image", str(images["fullimage"])], timeout=300), image=True)
        stage("firmware_verify")
        log("이미지 쓰기 완료. 버튼을 누르고 있다면 놓으세요. 정상 연결과 버전을 확인합니다.")
        rediscover()
        try:
            version = pm3.run("hw version", timeout=30).text
        except Pm3Error as e:
            raise Pm3Error("이미지 쓰기는 끝났지만 정상 연결 확인에 실패했습니다. 버튼을 놓고 USB를 다시 연결한 뒤 연결 확인을 실행하세요. 펌웨어 쓰기를 반복하지 마세요.\n" + str(e)) from None
        if not re.search(r"(?:\bos:|\bOS\.+)\s*[^\n]*" + SOURCE_REVISION, version, re.I) or "mismatch" in version.lower() or "does not match" in version.lower():
            raise Pm3Error("이미지 쓰기는 끝났지만 OS 버전 일치를 확인하지 못했습니다. 버튼을 놓고 USB를 다시 연결한 뒤 연결 확인을 실행하세요. 펌웨어 쓰기를 반복하지 마세요.")
        log("펌웨어 복구 및 장치 버전 확인 완료. 이제 원터치 시작으로 카드를 읽을 수 있습니다.")
        return {"connected": True, "port": pm3.port, "firmware_verified": True, "build": runtime.BUILD}
    except Exception as e:
        log("복구 중단: " + str(e))
        raise
    finally:
        try:
            cfg.out_path.mkdir(parents=True, exist_ok=True)
            (cfg.out_path / "firmware-repair.log").write_text("\n".join(lines), encoding="utf-8")
        except OSError:
            echo("복구 로그를 파일로 저장하지 못했습니다. 화면 로그를 보관하세요.")
