"""Proxmark3 클라이언트를 감싼다 — 찾고, 명령을 돌리고, 글자 출력을 돌려준다.

Proxmark3 Iceman 펌웨어/클라이언트를 쓴다. 클라이언트는 명령 한 줄을 돌리고 빠지는
`-c` 방식을 쓴다(`pm3 -c "hf mf info"`). 여러 명령은 하나의 `-c` 인자 안에서 세미콜론으로 구분한다.

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
import queue
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


class Pm3Error(Exception):
    pass


class DeviceNotFound(Pm3Error):
    pass


class FirmwareMismatch(Pm3Error):
    pass


# 흔한 설치 위치 — 윈도우(ProxSpace/릴리스)와 리눅스/맥을 함께 본다.
_WIN_GLOBS = [
    r"C:\ProxSpace\pm3\proxmark3\client\proxmark3.exe",
    r"C:\ProxSpace\pm3\proxmark3\client\build\proxmark3.exe",
    r"C:\ProxSpace\pm3\pm3.bat",
    r"C:\ProxSpace\pm3\client\proxmark3.exe",
    r"C:\ProxSpace\pm3\client\build\proxmark3.exe",
    r"C:\proxmark3\proxmark3.exe",
    r"C:\proxmark3\client\proxmark3.exe",
]


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


def _cheap_candidates(configured: str | None) -> list[str]:
    cands: list[str] = []
    for c in (configured, os.environ.get("AMSRFID_PM3"), _path_txt()):
        if c:
            cands.append(c.strip().strip('"'))
    from .runtime import installed_client
    managed = installed_client(_root())
    if managed:
        cands.append(managed)
    if cands:
        return cands  # Explicit configuration must not trigger installation searches.
    for name in (("proxmark3.exe", "pm3.bat") if os.name == "nt" else _NAMES):
        found = shutil.which(name)
        if found:
            cands.append(found)
    if os.name == "nt":
        for pat in _WIN_GLOBS:
            try:
                cands.extend(sorted(glob.glob(pat)))
            except OSError:
                pass
    else:
        cands.extend(_NIX_CANDIDATES)
    return cands


def _scan_roots() -> list[Path]:
    """클라이언트를 찾아볼 '흔한 폴더만'. 드라이브 루트(C:\\) 전체는 절대 훑지 않는다.

    과거 C:\\ 전체 os.walk 가 시스템을 멈추게/죽게 한 사례가 있어, 사용자가 보통 압축을 푸는
    몇몇 폴더만 얕게 본다.
    """
    roots: list[Path] = []
    if os.name == "nt":
        up = os.environ.get("USERPROFILE") or ""
        bases = []
        if up:
            bases += [up + r"\Downloads", up + r"\Desktop", up + r"\Documents", up]
        bases += [r"C:\ProxSpace", r"C:\proxmark3", r"C:\tools",
                  os.environ.get("ProgramFiles", ""), os.environ.get("ProgramFiles(x86)", "")]
        for b in bases:
            if b:
                roots.append(Path(b))
    else:
        for v in (os.environ.get("HOME"), "/opt", "/usr/local"):
            if v:
                roots.append(Path(v))
    # 이 도구 폴더의 이웃(형제 폴더)도 — 보통 proxmark 를 옆에 둔다.
    try:
        roots.append(_root().parent)
    except Exception:
        pass
    seen, out = set(), []
    for r in roots:
        k = str(r).lower()
        if k not in seen:
            try:
                if r.exists():
                    seen.add(k)
                    out.append(r)
            except OSError:
                pass
    return out


def deep_find_client(max_dirs: int = 4000, max_depth: int = 5) -> str | None:
    """흔한 폴더에서 pm3 실행 파일을 **얕은 glob 으로만** 찾는다(재귀 os.walk 안 함).

    과거 드라이브 전체 os.walk 가 시스템을 멈추게/죽게 한 사례가 있어, 재귀 탐색을 전부
    없앴다. 몇몇 폴더의 1~3단계 아래까지만 정해진 패턴으로 '파일 있나' 확인한다.
    (max_dirs·max_depth 는 호환용 인자일 뿐, 실제로는 쓰지 않는다.)
    """
    names = ("proxmark3.exe", "pm3.bat", "proxmark3", "pm3")
    hit: str | None = None
    for root in _scan_roots():
        for depth in (0, 1, 2):                     # 루트·1단계·2단계까지만(얕게)
            if hit:
                break
            for name in names:
                pat = os.path.join(str(root), *(["*"] * depth), name)
                try:
                    for cand in glob.glob(pat):
                        if Path(cand).is_file():
                            hit = cand
                            break
                except OSError:
                    continue
                if hit:
                    break
        if hit:
            break
    if hit:
        try:
            (_root() / "pm3_path.txt").write_text(hit, encoding="utf-8")
        except OSError:
            pass
    return hit


def find_client(configured: str | None = None, deep: bool = False) -> str:
    """pm3 실행 파일 경로를 돌려준다. 못 찾으면 DeviceNotFound.

    deep=True 면 흔한 위치에서 못 찾았을 때 제한된 깊이로 설치 폴더를 찾는다.
    """
    for c in _cheap_candidates(configured):
        if c and Path(c).is_file():
            return str(Path(c).resolve())
    if deep:
        found = deep_find_client()
        if found:
            return found
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


def _ps_run(script: str, timeout: float = 25):
    for exe in ("powershell", "pwsh"):
        try:
            return subprocess.run(
                [exe, "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True, timeout=timeout,
            )
        except (OSError, subprocess.SubprocessError):
            continue
    return None


def _pm3_match(pnpid: str) -> bool:
    u = (pnpid or "").upper()
    return any(("VID_" + v) in u and ("PID_" + p) in u for v, p in _PM3_USB_IDS)


# VID:PID 를 정수쌍으로도 — pyserial 비교용.
_PM3_VIDPID = {(int(v, 16), int(p, 16)) for v, p in _PM3_USB_IDS}


def _pyserial_ports() -> list[dict] | None:
    """pyserial 로 시리얼 포트를 나열한다(Proxmark3GUI·ProxSpace 등이 쓰는 검증된 방식).

    pyserial 이 없으면 None(=대체 수단으로 넘어가라는 신호)을 돌려준다.
    """
    try:
        from serial.tools.list_ports import comports  # type: ignore
    except Exception:
        return None
    out = []
    try:
        ports = comports()
    except OSError as e:
        raise DeviceNotFound("COM 포트 목록을 읽지 못했습니다: %s. amsrfid.toml 에 port 를 직접 지정할 수 있습니다." % e) from None
    for p in ports:
        manuf = getattr(p, "manufacturer", "") or ""
        serial = getattr(p, "serial_number", "") or ""
        desc = " ".join(filter(None, [
            getattr(p, "description", "") or "",
            manuf,
            getattr(p, "product", "") or "",
            serial,
            getattr(p, "hwid", "") or "",
        ]))
        out.append({
            "device": p.device,
            "vid": getattr(p, "vid", None),
            "pid": getattr(p, "pid", None),
            "desc": desc,
            "manufacturer": manuf,
            "serial": serial,
        })
    return out


def _port_is_pm3(info: dict) -> bool:
    if info.get("vid") and info.get("pid") and (info["vid"], info["pid"]) in _PM3_VIDPID:
        return True
    # pm3 래퍼의 udev/ioreg 벤더 교차확인과 같은, 설명 substring 보다 강한 신호
    if "proxmark.org" in (info.get("manufacturer") or "").lower():
        return True
    d = (info.get("desc") or "").lower()
    return "proxmark" in d or "iceman" in d


def _com_of(name: str) -> str | None:
    m = re.search(r"\((COM\d+)\)", name or "", re.I)
    return m.group(1).upper() if m else None


def _win_scan() -> list[tuple[str, str, str]]:
    """윈도우의 모든 PnP 장치를 한 번에 긁어 (name, errcode, pnpid) 로 돌려준다.

    필터링은 PowerShell 이 아니라 파이썬에서 한다 — 따옴표/& 때문에 쿼리가 깨지는 일을 막는다.
    Win32_SerialPort 는 USB CDC(프록시마크 같은) 포트를 종종 누락하므로 쓰지 않고,
    더 완전한 Win32_PnPEntity 를 쓴다.
    """
    ps = ("Get-CimInstance Win32_PnPEntity | ForEach-Object { "
          "\"$($_.Name)|$($_.ConfigManagerErrorCode)|$($_.PNPDeviceID)\" }")
    out = _ps_run(ps, timeout=30)
    rows: list[tuple[str, str, str]] = []
    if out is None:
        return rows
    for line in (out.stdout or b"").decode("utf-8", "replace").splitlines():
        parts = line.split("|")
        if len(parts) >= 3:
            rows.append((parts[0].strip(), parts[1].strip(), "|".join(parts[2:]).strip()))
    return rows


def _reg_serialcomm() -> list[str]:
    """레지스트리에서 COM 포트 목록을 읽는다(PowerShell 이 없을 때의 대비). 이름만 나온다."""
    if os.name != "nt":
        return []
    try:
        out = subprocess.run(
            ["reg", "query", r"HKLM\HARDWARE\DEVICEMAP\SERIALCOMM"],
            capture_output=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    coms = []
    for line in (out.stdout or b"").decode("utf-8", "replace").splitlines():
        m = re.search(r"(COM\d+)", line)
        if m:
            coms.append(m.group(1).upper())
    return sorted(set(coms))


def detect_device(include_pnp: bool = False) -> dict:
    """꽂힌 Proxmark3 를 '드라이버 유무까지' 본다.

    1순위: pyserial 로 PM3 의 COM 포트를 찾는다(Proxmark3GUI·ProxSpace 와 같은 검증된 방식).
    기본은 pyserial 포트 열거만 한다. include_pnp=True 를 명시할 때만
    Windows 전체 PnP 조회를 허용한다. 포트를 직접 열지는 않는다.
    """
    res = {"present": False, "com": None, "needs_driver": False, "name": "", "status": ""}

    # 1순위: pyserial (크로스플랫폼, USB-CDC 포트도 안 놓침)
    ports = _pyserial_ports()
    if ports is not None:
        for pi in ports:
            if _port_is_pm3(pi):
                res["present"] = True
                res["com"] = pi["device"]
                res["name"] = pi.get("desc", "")
                return res

    if os.name != "nt":
        # 리눅스/맥: pyserial 이 없을 때만 장치 노드로 대체
        if ports is None:
            p = detect_port()
            res["present"] = bool(p)
            res["com"] = p
        return res

    # Windows: COM 으로 안 잡혔다 → PnP 전체에서 PM3 를 찾아 '드라이버 필요'인지 본다
    if not include_pnp:
        return res
    rows = _win_scan()
    pm3 = [(n, e, p) for (n, e, p) in rows if _pm3_match(p)]
    for (n, e, p) in rows:
        if ("proxmark" in n.lower() or "pm3" in n.lower()) and (n, e, p) not in pm3:
            pm3.append((n, e, p))
    if pm3:
        res["present"] = True
        res["name"] = pm3[0][0]
        res["status"] = pm3[0][1]
        for (n, e, p) in pm3:
            com = _com_of(n)
            if com:
                res["com"] = com            # pyserial 이 없어도 PnP 이름에서 COM 을 건짐
                return res
        res["needs_driver"] = True          # 장치는 있는데 COM 이 없다 → 드라이버/케이블 문제
    return res


def detect_port() -> str | None:
    """Proxmark3 가 꽂힌 시리얼 포트를 자동 탐지한다. 못 찾으면 None."""
    if os.name == "nt":
        return detect_device().get("com")
    # 리눅스/맥: pyserial 우선, 없으면 장치 노드.
    ports = _pyserial_ports()
    if ports is not None:
        for pi in ports:
            if _port_is_pm3(pi):
                return pi["device"]
    for pat in ("/dev/pm3-*", "/dev/ttyACM*", "/dev/cu.usbmodem*", "/dev/tty.usbmodem*", "/dev/ttyUSB*"):
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[0]
    return None


def _auto_port() -> str | None:
    return detect_port()


def diagnostics(configured: str | None = None, port: str | None = None) -> dict:
    """진단용 — 도구가 '지금 무엇을 보는지' 전부 모아 돌려준다(USB 인식 문제 추적)."""
    d: dict = {"os": os.name, "platform": sys.platform, "python": sys.version.split()[0]}
    ports = _pyserial_ports()
    d["pyserial"] = ports is not None
    d["serial_ports"] = ports or []          # pyserial 이 본 모든 포트(없으면 [])
    if os.name == "nt":
        d["powershell"] = _ps_run("'ok'") is not None
        rows = _win_scan()
        d["pnp_count"] = len(rows)
        d["com_ports"] = [{"com": _com_of(n), "name": n, "pnpid": p}
                          for (n, e, p) in rows if _com_of(n)]
        d["pm3_devices"] = [{"name": n, "errcode": e, "pnpid": p}
                            for (n, e, p) in rows if _pm3_match(p) or "proxmark" in n.lower()]
        d["registry_com"] = _reg_serialcomm()
    else:
        d["powershell"] = False
        d["com_ports"] = [{"com": None, "name": g, "pnpid": g}
                          for pat in ("/dev/ttyACM*", "/dev/pm3-*", "/dev/ttyUSB*")
                          for g in sorted(glob.glob(pat))]
        d["pm3_devices"] = []
        d["registry_com"] = []
    d["device"] = {"present": False, "com": None, "needs_driver": False, "name": ""}
    for info in ports or []:
        if _port_is_pm3(info):
            d["device"].update(present=True, com=info["device"], name=info.get("desc", ""))
            break
    if not d["device"]["present"] and d["pm3_devices"]:
        info = d["pm3_devices"][0]
        com = _com_of(info["name"])
        d["device"].update(present=True, com=com, needs_driver=not bool(com), name=info["name"])
    d["configured_port"] = port
    try:
        d["client"] = find_client(configured)
    except DeviceNotFound:
        d["client"] = None
    # 흔한 진짜 원인 힌트
    if not d["device"].get("present"):
        d["hint"] = ("장치가 안 보입니다. 1) '데이터 전송용' USB 케이블인지 확인(충전 전용은 안 됨) "
                     "2) 다른 USB 포트에 꽂기 3) Win7 이면 드라이버 설치. Win10/11 은 꽂으면 "
                     "보통 자동 인식됩니다.")
    return d


def default_inf() -> Path:
    return _root() / "drivers" / "proxmark3.inf"


def install_driver(inf: str | Path | None = None) -> tuple[bool, str]:
    """드라이버는 **실행으로 설치하지 않는다** — 안내만 한다(pnputil 호출 제거).

    이 도구는 시스템(커널)을 건드리지 않는다. Windows 10/11 은 Proxmark3(USB CDC)를 꽂으면
    내장 usbser 로 자동 인식한다. 안 잡히면 대개 '충전 전용 케이블'이거나, 예전에 Zadig/WinUSB
    드라이버를 깐 적이 있어 장치가 'Ports'에서 빠진 경우다(이 경우 장치관리자에서 장치 제거 +
    '드라이버 소프트웨어 삭제' 후 다시 꽂으면 usbser 로 재인식된다).
    """
    guide = (
        "이 도구는 드라이버를 자동 설치하지 않습니다(시스템 안정성). 포트가 안 잡히면:\n"
        "  1) '데이터 전송용' USB 케이블인지 (충전 전용 불가) · 본체 USB 포트인지 확인\n"
        "  2) 예전에 Zadig/WinUSB 를 깐 적 있으면: 장치관리자에서 Proxmark3 장치 → 제거 →\n"
        "     '이 장치의 드라이버 소프트웨어를 삭제' 체크 → 뽑았다 다시 꽂기 (usbser 로 재인식)\n"
        "  3) Win7 등: 장치관리자 → 드라이버 업데이트 → drivers\\proxmark3.inf 수동 지정"
    )
    return (False, guide)


def find_firmware_images(client: str) -> dict:
    """클라이언트 근처에서 펌웨어 이미지(fullimage.elf·bootrom.elf)를 찾는다.

    ProxSpace/릴리스 배치: proxmark3.exe 는 보통 client/ 에, .elf 는 armsrc/obj·bootrom/obj
    또는 릴리스면 바로 옆에 있다. 클라이언트 폴더의 위쪽 3단계까지 뒤진다.
    """
    out = {"fullimage": None, "bootrom": None}
    base = Path(client).resolve().parent
    # Only known package layouts; never recurse into an ancestor drive/home.
    roots = [base, base.parent]
    if base.name.lower() == "build":
        roots.append(base.parent.parent)
    for root in roots:
        for name, key, subdir in (("fullimage.elf", "fullimage", "armsrc"),
                                  ("bootrom.elf", "bootrom", "bootrom")):
            for candidate in (root / name, root / subdir / "obj" / name):
                if not out[key] and candidate.is_file():
                    out[key] = str(candidate)
    return out


# 터미널 색상(ANSI) 이스케이프 — 문자열 매칭 전에 벗겨 낸다(pm3.bat 빌드가 색을 흘릴 때 대비).
_ANSI = re.compile(r"(\x9B|\x1B\[)[0-?]*[ -/]*[@-~]")

# 명시적인 연결 실패만 감지한다. 정상 'Using serial port' 배너는 제외한다.
_DISCONNECT_HINTS = (
    "offline mode", "cannot communicate with the proxmark", "comm error",
    "failed to open serial", "unable to open serial", "could not open port",
    "proxmark3 not found", "device not found", "communication timeout",
)


def _looks_disconnected(text: str) -> bool:
    t = (text or "").lower()
    return any(h in t for h in _DISCONNECT_HINTS)


def quoted_path(path: str | Path) -> str:
    value = str(Path(path).resolve())
    if any(c in value for c in ('"', ';', '\r', '\n')):
        raise Pm3Error("파일 경로에 큰따옴표·세미콜론·줄바꿈을 사용할 수 없습니다.")
    return '"' + value + '"'


@dataclass
class Pm3Result:
    returncode: int
    stdout: str
    stderr: str

    @property
    def text(self) -> str:
        raw = self.stdout + ("\n" + self.stderr if self.stderr else "")
        return _ANSI.sub("", raw)


@dataclass
class Pm3:
    """pm3 클라이언트 한 대를 가리킨다."""

    client: str
    port: str | None = None
    workdir: Path | None = None
    extra_args: list[str] = field(default_factory=list)
    echo: Callable[[str], None] | None = None

    @classmethod
    def locate(
        cls,
        configured: str | None = None,
        port: str | None = None,
        workdir: Path | None = None,
        extra_args: list[str] | None = None,
        deep: bool = False,
    ) -> "Pm3":
        return cls(
            client=find_client(configured, deep=deep),
            port=port,
            workdir=workdir,
            extra_args=list(extra_args or []),
        )

    def _is_wrapper(self) -> bool:
        """`pm3`/`pm3.bat` 래퍼는 포트를 스스로 찾는다. 날것 proxmark3 는 포트가 필요."""
        name = Path(self.client).name.lower()
        return name.startswith("pm3")

    def _resolved_port(self) -> str | None:
        """포트를 한 번 찾으면 인스턴스에 캐시한다(매 명령마다 재탐색 방지)."""
        if not self.port:
            self.port = _auto_port()
        return self.port

    def _build_args(self, commands: list[str]) -> list[str]:
        args = [self.client]
        # 포트를 알면 래퍼(pm3/pm3.bat)든 날것(proxmark3.exe)이든 -p 로 넘긴다.
        # 래퍼의 자체 자동탐지는 Easy(502D:502D)를 놓치므로, 우리가 찾은 포트를 직접 준다.
        port = self._resolved_port()
        if not port:
            raise DeviceNotFound("Proxmark3 포트를 찾지 못했습니다. amsrfid.toml 의 port 를 지정하거나 상태 확인을 실행하세요.")
        args.extend(["-p", port])
        args.extend(self.extra_args)
        if not commands or any(not c.strip() for c in commands):
            raise Pm3Error("실행할 pm3 명령이 없습니다.")
        args.extend(["-f", "-c", "; ".join(commands)])
        return args

    def _run_subprocess(self, args: list[str], timeout: float) -> Pm3Result:
        from .runtime import client_environment
        if self.echo:
            self.echo("▶ " + " ".join(args[1:]))
        try:
            if self.workdir:
                self.workdir.mkdir(parents=True, exist_ok=True)
            process = subprocess.Popen(
                args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, cwd=str(self.workdir) if self.workdir else None,
                env=client_environment(self.client),
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except OSError as e:
            raise DeviceNotFound("pm3 를 실행하지 못했습니다: %s" % e) from None
        chunks: queue.Queue = queue.Queue()
        def read_output():
            try:
                # Universal newlines also expose CR-only progress updates.
                import io
                with io.TextIOWrapper(process.stdout, encoding="utf-8", errors="replace") as stream:
                    for line in stream:
                        chunks.put(line)
            finally:
                chunks.put(None)
        reader = threading.Thread(target=read_output, daemon=True)
        reader.start()
        deadline = time.monotonic() + timeout
        lines = []
        finished = False
        try:
            while not finished:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(args, timeout)
                try:
                    line = chunks.get(timeout=min(remaining, 0.2))
                except queue.Empty:
                    continue
                if line is None:
                    finished = True
                else:
                    lines.append(line)
                    if self.echo:
                        self.echo(_ANSI.sub("", line).rstrip())
            process.wait(timeout=max(0.01, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            result = Pm3Result(-1, "".join(lines), "시간 제한 초과")
            self._save_log(args, result)
            raise Pm3Error("pm3 명령 시간 제한(%s초) 초과. 자동 재시도하지 않습니다.\n%s"
                           % (timeout, result.text[-2000:])) from None
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            reader.join(timeout=1)
        result = Pm3Result(process.returncode, "".join(lines), "")
        self._save_log(args, result)
        return result

    def _save_log(self, args: list[str], result: Pm3Result) -> None:
        if self.workdir:
            try:
                (self.workdir / "last-pm3.log").write_text(
                    "Command: %r\nExit: %s\n%s" % (args, result.returncode, result.text),
                    encoding="utf-8")
            except OSError:
                pass  # Log failure must not mask the client's actual result.

    def run(self, commands: str | list[str], timeout: float = 180) -> Pm3Result:
        """명령(들)을 차례로 돌리고 출력을 모아 돌려준다.

        통신이 끊겨도 명령을 자동 재실행하지 않는다(쓰기 중복 실행 방지).
        """
        if isinstance(commands, str):
            commands = [commands]
        # Never replay commands: a write can have completed before disconnection.
        result = self._run_subprocess(self._build_args(commands), timeout)
        if result.returncode != 0 or _looks_disconnected(result.text):
            if "capabilities structure version" in result.text.lower():
                raise FirmwareMismatch(
                    "장치 펌웨어와 클라이언트의 통신 규격이 다릅니다. COM 포트 통신은 확인됐습니다.\n"
                    "'Easy 펌웨어 복구'에서 같은 배포본으로 부트로더·펌웨어를 맞춰 주세요.\n%s" % result.text[-2000:])
            if "cannot communicate with the proxmark" in result.text.lower():
                raise Pm3Error(
                    "포트 %s 는 열렸지만 장치 통신 검사에 실패했습니다. 클라이언트 설치는 완료된 상태입니다.\n"
                    "USB를 뽑았다가 Easy 버튼을 누르지 않고 다시 연결한 뒤 '자동 준비·연결 확인'을 실행하세요.\n"
                    "계속 실패하면 '통신 상세 점검'을 실행하고 out/connection-debug.log 를 확인하세요.\n"
                    "구형 펌웨어·부트로더 모드·USB 통신 문제를 구분해야 하며, 이 오류만으로 Windows 11이나 드라이버 문제를 확정할 수 없습니다.\n%s"
                    % (self.port, result.text[-2000:]))
            raise Pm3Error("pm3 실행/연결 실패 (포트 %s, 종료 코드 %s). 다른 pm3 프로그램을 종료하고 경로·COM 포트를 확인하세요.\n%s"
                           % (self.port, result.returncode, result.text[-2000:]))
        return result

    def run_raw(self, extra: list[str], timeout: float = 300) -> Pm3Result:
        """`-c` 없이 클라이언트를 직접 호출한다(플래싱 등). 플래싱은 자동 재시도하지 않는다."""
        args = [self.client]
        port = self._resolved_port()
        if not port:
            raise DeviceNotFound("Proxmark3 포트를 찾지 못했습니다. amsrfid.toml 의 port 를 지정하거나 상태 확인을 실행하세요.")
        args.extend(["-p", port])
        args.extend(self.extra_args)
        args.extend(extra)
        return self._run_subprocess(args, timeout)

    # -- 장치/카드 상태 ----------------------------------------------------

    def device_present(self) -> bool:
        """Proxmark3 하드웨어가 붙어 있고 말이 통하는지."""
        try:
            res = self.run("hw version", timeout=30)
        except Pm3Error:
            return False
        t = res.text.lower()
        return bool(re.search(r"\bos:\s*\S", t))

    def firmware_version(self) -> str:
        """`hw version` 출력을 돌려준다(펌웨어/클라이언트 버전 확인용)."""
        try:
            return self.run("hw version", timeout=30).text
        except Pm3Error:
            return ""

    def supports_fm11rf08s(self) -> bool:
        """펌웨어가 FM11RF08S 백도어/isen 을 지원하는지(hf mf isen 도움말로 간접 확인)."""
        try:
            t = self.run("hf mf isen --help", timeout=20).text.lower()
        except Pm3Error:
            return False
        return "collect_fm11rf08s" in t or "fm11rf08s" in t

    def card_present(self) -> bool:
        """14a 태그(카드)가 안테나 위에 있는지."""
        res = self.run("hf 14a info", timeout=30)
        t = res.text
        low = t.lower()
        if "failed" in low or "no answer" in low or "no known" in low:
            return False
        # 카드가 있으면 UID/ATQA/SAK 가 찍힌다.
        return bool(re.search(r"\bUID\b", t)) and "ATQA" in t
