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


# 흔한 설치 위치 — 윈도우(ProxSpace/릴리스)와 리눅스/맥을 함께 본다.
_WIN_GLOBS = [
    r"C:\ProxSpace\pm3\pm3.bat",
    r"C:\ProxSpace\pm3\proxmark3.exe",
    r"C:\ProxSpace\**\pm3.bat",
    r"C:\ProxSpace\**\proxmark3.exe",
    r"C:\Program Files*\proxmark3\**\pm3.bat",
    r"C:\Program Files*\proxmark3\**\proxmark3.exe",
    r"C:\proxmark3\**\pm3.bat",
    r"C:\proxmark3\**\proxmark3.exe",
    r"C:\tools\**\proxmark3.exe",
]


def _win_user_globs() -> list[str]:
    """사용자 폴더·다운로드 밑에 풀어 둔 릴리스도 본다."""
    pats: list[str] = []
    for base in filter(None, [os.environ.get("USERPROFILE"), os.environ.get("LOCALAPPDATA")]):
        pats += [
            base + r"\**\pm3.bat",
            base + r"\**\proxmark3.exe",
        ]
    return pats
_NIX_CANDIDATES = [
    "/usr/local/bin/pm3",
    "/usr/bin/pm3",
    "/opt/proxmark3/pm3",
    "/usr/local/bin/proxmark3",
]
_NAMES = ("pm3", "pm3.bat", "proxmark3", "proxmark3.exe")


def _root() -> Path:
    return Path(__file__).resolve().parent.parent


def _path_txt() -> str:
    """pm3_path.txt 한 줄로 경로를 지정하는 가장 쉬운 방법(비전문가용)."""
    try:
        return (_root() / "pm3_path.txt").read_text(encoding="utf-8-sig").strip()
    except OSError:
        return ""


def find_client(configured: str | None = None) -> str:
    """pm3 실행 파일 경로를 돌려준다. 못 찾으면 DeviceNotFound."""
    cands: list[str] = []
    for c in (configured, os.environ.get("AMSRFID_PM3"), _path_txt()):
        if c:
            cands.append(c.strip().strip('"'))
    for name in _NAMES:
        found = shutil.which(name)
        if found:
            cands.append(found)
    if os.name == "nt":
        for pat in _WIN_GLOBS + _win_user_globs():
            try:
                cands.extend(sorted(glob.glob(pat, recursive=True)))
            except OSError:
                pass
    else:
        cands.extend(_NIX_CANDIDATES)
    for c in cands:
        if c and Path(c).is_file():
            return c
    raise DeviceNotFound(
        "Proxmark3 클라이언트(pm3)를 찾지 못했습니다. 다음 중 하나로 경로를 알려 주세요:\n"
        "  · 폴더에 pm3_path.txt 를 만들고 pm3.bat(또는 proxmark3.exe) 전체 경로를 한 줄로 적기\n"
        "  · amsrfid.toml 의 pm3_path = \"...\"\n"
        "  · 환경변수 AMSRFID_PM3\n"
        "예) C:\\ProxSpace\\pm3\\pm3.bat  또는  C:\\proxmark3\\proxmark3.exe"
    )


# Proxmark3 의 공식 USB VID:PID (RRG proxmark3 driver/proxmark3.inf, pm3 래퍼, PM3_USB_IDS).
#   9AC4:4B8F = 정품(proxmark.org) · 2D2D:504D = 구형 부트로더 · 502D:502D = PM3 Easy
_PM3_USB_IDS = (("9AC4", "4B8F"), ("2D2D", "504D"), ("502D", "502D"))


def _win_detect_port() -> str | None:
    """공식 pm3 래퍼와 똑같은 방식: Win32_SerialPort 에서 PM3 VID:PID 로 COM 을 찾는다."""
    cond = " -or ".join("$_.PNPDeviceID -like '*VID_%s&PID_%s*'" % (v, p) for v, p in _PM3_USB_IDS)
    ps = ("Get-CimInstance -ClassName Win32_SerialPort | "
          "Where-Object {%s} | Select-Object -ExpandProperty DeviceID" % cond)
    for exe in ("powershell", "pwsh"):
        try:
            out = subprocess.run(
                [exe, "-NoProfile", "-NonInteractive", "-Command", ps],
                capture_output=True, timeout=15,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        for line in (out.stdout or b"").decode("utf-8", "replace").splitlines():
            m = re.search(r"(COM\d+)", line.strip(), re.I)
            if m:
                return m.group(1).upper()
        return None
    return None


def detect_port() -> str | None:
    """Proxmark3 가 꽂힌 시리얼 포트를 공식 방식으로 자동 탐지한다. 못 찾으면 None."""
    if os.name == "nt":
        return _win_detect_port()
    # 리눅스/맥: 공식 pm3 래퍼는 udev 가 만든 /dev/pm3-* 를 먼저 보고, 없으면 ACM/usbmodem 을 본다.
    for pat in ("/dev/pm3-*", "/dev/ttyACM*", "/dev/tty.usbmodem*", "/dev/cu.usbmodem*", "/dev/ttyUSB*"):
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[0]
    return None


def _auto_port() -> str | None:
    return detect_port()


def _ps_run(script: str, timeout: float = 20):
    for exe in ("powershell", "pwsh"):
        try:
            return subprocess.run(
                [exe, "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True, timeout=timeout,
            )
        except (OSError, subprocess.SubprocessError):
            continue
    return None


def detect_device() -> dict:
    """꽂힌 Proxmark3 를 '드라이버 유무까지' 본다(Win32_PnPEntity 전체에서 VID:PID 로).

    돌려주는 것: {present, com, needs_driver, name, status}
      · present      : PM3 USB 장치가 보이는가(드라이버 없어도)
      · com          : COM 포트(드라이버가 붙어 포트가 생겼을 때)
      · needs_driver : 장치는 보이는데 COM 포트가 없다(=드라이버 설치 필요)
    """
    res = {"present": False, "com": None, "needs_driver": False, "name": "", "status": ""}
    if os.name != "nt":
        p = detect_port()
        res["present"] = bool(p)
        res["com"] = p
        return res
    cond = " -or ".join("$_.PNPDeviceID -like '*VID_%s&PID_%s*'" % (v, p) for v, p in _PM3_USB_IDS)
    ps = ("Get-CimInstance Win32_PnPEntity | Where-Object {%s} | "
          "ForEach-Object { \"$($_.Name)|$($_.ConfigManagerErrorCode)|$($_.PNPDeviceID)\" }" % cond)
    out = _ps_run(ps)
    if out is None:
        return res
    for line in (out.stdout or b"").decode("utf-8", "replace").splitlines():
        line = line.strip()
        if not line:
            continue
        name, _, rest = line.partition("|")
        errcode, _, _pnp = rest.partition("|")
        res["present"] = True
        res["name"] = name.strip()
        res["status"] = errcode.strip()
        m = re.search(r"\((COM\d+)\)", name, re.I)
        if m:
            res["com"] = m.group(1).upper()
            res["needs_driver"] = False
            return res                     # COM 포트까지 있으면 완성 — 바로 반환
        # COM 이 없거나 오류코드 28(드라이버 없음)이면 드라이버 필요
        res["needs_driver"] = True
    return res


def default_inf() -> Path:
    return _root() / "drivers" / "proxmark3.inf"


def install_driver(inf: str | Path | None = None) -> tuple[bool, str]:
    """공식 proxmark3.inf 를 pnputil 로 설치한다(관리자 권한 UAC). Windows 전용."""
    if os.name != "nt":
        return (False, "드라이버 설치는 Windows 에서만 필요합니다.")
    infp = Path(inf) if inf else default_inf()
    if not infp.is_file():
        return (False, "드라이버 파일을 찾지 못했습니다: %s" % infp)
    # pnputil 을 관리자 권한으로 띄운다(UAC 창이 뜬다). 끝날 때까지 기다려 종료코드를 받는다.
    ps = (
        "$p = Start-Process pnputil -ArgumentList '/add-driver','%s','/install' "
        "-Verb RunAs -Wait -PassThru; $p.ExitCode" % str(infp)
    )
    out = _ps_run(ps, timeout=180)
    if out is None:
        return (False, "PowerShell 을 실행하지 못했습니다.")
    txt = (out.stdout or b"").decode("utf-8", "replace").strip()
    err = (out.stderr or b"").decode("utf-8", "replace").strip()
    code = txt.splitlines()[-1].strip() if txt else ""
    # pnputil: 0=성공, 3010/259=성공(재부팅/대기), 1=사용자가 UAC 취소 등
    if code in ("0", "3010", "259"):
        return (True, "드라이버 설치 완료(코드 %s). 장치를 다시 꽂거나 잠시 기다리면 COM 포트가 잡힙니다." % code)
    if "canceled" in err.lower() or "취소" in err or code == "":
        return (False, "드라이버 설치가 취소되었거나 관리자 권한을 얻지 못했습니다(UAC 에서 '예'를 눌러 주세요).")
    return (False, "드라이버 설치 실패(코드 %s). %s" % (code or "?", err[-300:]))


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
