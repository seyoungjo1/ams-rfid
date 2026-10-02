"""Proxmark3 클라이언트를 감싼다 — 찾고, 명령을 돌리고, 글자 출력을 돌려준다.

Proxmark3 Iceman 펌웨어/클라이언트를 쓴다. 클라이언트는 명령 한 줄을 돌리고 빠지는
`-c` 방식을 쓴다(`pm3 -c "hf mf info"`). 여러 줄은 `-c` 를 여러 번 넘겨 차례로 돌린다.

실행 파일 찾는 순서
  1) config 의 pm3_path
  2) 환경변수 AMSRFID_PM3
  3) PATH 의 pm3 / pm3.bat / proxmark3 / proxmark3.exe
  4) 흔한 설치 위치(ProxSpace, /usr/local/bin 등)

`pm3` 래퍼는 포트를 알아서 찾는다. 날것 `proxmark3` 만 있으면 포트가 필요하므로
config.port(없으면 자동 탐색)를 붙인다.
"""
from __future__ import annotations

import glob
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path


class Pm3Error(Exception):
    pass


class DeviceNotFound(Pm3Error):
    pass


# 흔한 설치 위치 — 윈도우(ProxSpace)와 리눅스/맥을 함께 본다.
_WIN_GLOBS = [
    r"C:\ProxSpace\pm3\pm3.bat",
    r"C:\ProxSpace\pm3\proxmark3.exe",
    r"C:\Program Files\proxmark3\pm3.bat",
    r"C:\Program Files\proxmark3\proxmark3.exe",
    r"C:\Program Files*\proxmark3\*\pm3.bat",
]
_NIX_CANDIDATES = [
    "/usr/local/bin/pm3",
    "/usr/bin/pm3",
    "/opt/proxmark3/pm3",
    "/usr/local/bin/proxmark3",
]
_NAMES = ("pm3", "pm3.bat", "proxmark3", "proxmark3.exe")


def find_client(configured: str | None = None) -> str:
    """pm3 실행 파일 경로를 돌려준다. 못 찾으면 DeviceNotFound."""
    cands: list[str] = []
    if configured:
        cands.append(configured)
    env = os.environ.get("AMSRFID_PM3")
    if env:
        cands.append(env)
    for name in _NAMES:
        found = shutil.which(name)
        if found:
            cands.append(found)
    if os.name == "nt":
        for pat in _WIN_GLOBS:
            cands.extend(sorted(glob.glob(pat)))
    else:
        cands.extend(_NIX_CANDIDATES)
    for c in cands:
        if c and Path(c).is_file():
            return c
    raise DeviceNotFound(
        "Proxmark3 클라이언트(pm3)를 찾지 못했습니다. 설치했는지 확인하거나, "
        "amsrfid.toml 의 pm3_path 또는 환경변수 AMSRFID_PM3 로 경로를 알려 주세요."
    )


def _auto_port() -> str | None:
    """pm3 래퍼가 아닌 날것 proxmark3 를 쓸 때 붙일 시리얼 포트를 추정한다."""
    if os.name == "nt":
        # 윈도우는 COM 번호를 확실히 알기 어렵다 — pm3 래퍼가 처리하게 둔다.
        return None
    for pat in ("/dev/ttyACM*", "/dev/ttyUSB*", "/dev/tty.usbmodem*", "/dev/cu.usbmodem*"):
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[0]
    return None


@dataclass
class Pm3Result:
    returncode: int
    stdout: str
    stderr: str

    @property
    def text(self) -> str:
        return self.stdout + ("\n" + self.stderr if self.stderr else "")


@dataclass
class Pm3:
    """pm3 클라이언트 한 대를 가리킨다."""

    client: str
    port: str | None = None
    workdir: Path | None = None
    extra_args: list[str] = field(default_factory=list)

    @classmethod
    def locate(
        cls,
        configured: str | None = None,
        port: str | None = None,
        workdir: Path | None = None,
        extra_args: list[str] | None = None,
    ) -> "Pm3":
        return cls(
            client=find_client(configured),
            port=port,
            workdir=workdir,
            extra_args=list(extra_args or []),
        )

    def _is_wrapper(self) -> bool:
        """`pm3`/`pm3.bat` 래퍼는 포트를 스스로 찾는다. 날것 proxmark3 는 포트가 필요."""
        name = Path(self.client).name.lower()
        return name.startswith("pm3")

    def _build_args(self, commands: list[str]) -> list[str]:
        args = [self.client]
        if not self._is_wrapper():
            port = self.port or _auto_port()
            if port:
                args.append(port)
        args.extend(self.extra_args)
        for c in commands:
            args.extend(["-c", c])
        return args

    def run(self, commands: str | list[str], timeout: float = 180) -> Pm3Result:
        """명령(들)을 차례로 돌리고 출력을 모아 돌려준다."""
        if isinstance(commands, str):
            commands = [commands]
        args = self._build_args(commands)
        try:
            done = subprocess.run(
                args,
                cwd=str(self.workdir) if self.workdir else None,
                capture_output=True,
                timeout=timeout,
            )
        except FileNotFoundError as e:
            raise DeviceNotFound("pm3 를 실행하지 못했습니다: %s" % e) from None
        except subprocess.TimeoutExpired:
            raise Pm3Error(
                "pm3 명령이 %.0f초 안에 끝나지 않았습니다: %s" % (timeout, "; ".join(commands))
            ) from None
        out = (done.stdout or b"").decode("utf-8", "replace")
        err = (done.stderr or b"").decode("utf-8", "replace")
        return Pm3Result(done.returncode, out, err)

    # -- 장치/카드 상태 ----------------------------------------------------

    def device_present(self) -> bool:
        """Proxmark3 하드웨어가 붙어 있고 말이 통하는지."""
        try:
            res = self.run("hw version", timeout=30)
        except Pm3Error:
            return False
        t = res.text.lower()
        return ("proxmark3" in t and "os:" in t) or "firmware" in t or "client:" in t

    def card_present(self) -> bool:
        """14a 태그(카드)가 안테나 위에 있는지."""
        try:
            res = self.run("hf 14a info", timeout=30)
        except Pm3Error:
            return False
        t = res.text
        low = t.lower()
        if "failed" in low or "no answer" in low or "no known" in low:
            return False
        # 카드가 있으면 UID/ATQA/SAK 가 찍힌다.
        return bool(re.search(r"\bUID\b", t)) and "ATQA" in t
