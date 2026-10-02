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


def _cheap_candidates(configured: str | None) -> list[str]:
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
    return cands


# 깊은 탐색에서 건너뛸(느리고 의미 없는) 디렉터리 이름들.
_SKIP_DIRS = {
    "windows", "$recycle.bin", "system volume information", "node_modules", ".git",
    "appdata", "winsxs", "assembly", "installer", "temp", "tmp", "cache",
    "microsoft", "packages", "program files (arm)",
}
_TARGET_NAMES = {"proxmark3.exe", "pm3.bat", "pm3", "proxmark3"}


def _scan_roots() -> list[Path]:
    roots: list[Path] = []
    if os.name == "nt":
        # 사용자 폴더 먼저(보통 여기에 풀어 둠), 그다음 고정 드라이브 루트.
        for env in ("USERPROFILE", "LOCALAPPDATA", "ProgramFiles", "ProgramFiles(x86)"):
            v = os.environ.get(env)
            if v:
                roots.append(Path(v))
        import string
        for d in string.ascii_uppercase:
            p = Path("%s:\\" % d)
            try:
                if p.exists():
                    roots.append(p)
            except OSError:
                pass
    else:
        for v in (os.environ.get("HOME"), "/opt", "/usr/local"):
            if v:
                roots.append(Path(v))
    # 중복 제거(순서 유지)
    seen, out = set(), []
    for r in roots:
        k = str(r).lower()
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out


def deep_find_client(max_dirs: int = 60000, max_depth: int = 7) -> str | None:
    """흔한 위치에서 못 찾았을 때, 드라이브/사용자 폴더를 제한적으로 뒤져 pm3 실행 파일을 찾는다.

    사용자가 '어딘가 풀어 둔' Proxmark3 를 자동으로 찾아내기 위한 마지막 수단.
    깊이·개수를 제한하고 시스템/거대 폴더는 건너뛰어 과하지 않게 돈다. 찾으면 그 경로를
    pm3_path.txt 에 적어 다음부터는 즉시 찾게 한다.
    """
    seen_dirs = 0
    hit: str | None = None
    for root in _scan_roots():
        base_depth = len(root.parts)
        try:
            walker = os.walk(root)
        except OSError:
            continue
        for cur, dirs, files in walker:
            seen_dirs += 1
            if seen_dirs > max_dirs:
                break
            depth = len(Path(cur).parts) - base_depth
            if depth >= max_depth:
                dirs[:] = []
            # 시스템/거대 폴더는 안 들어간다
            dirs[:] = [d for d in dirs if d.lower() not in _SKIP_DIRS and not d.startswith("$")]
            low = {f.lower(): f for f in files}
            for target in ("proxmark3.exe", "pm3.bat", "pm3", "proxmark3"):
                if target in low:
                    cand = str(Path(cur) / low[target])
                    if Path(cand).is_file():
                        hit = cand
                        break
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

    deep=True 면 흔한 위치에서 못 찾았을 때 드라이브/사용자 폴더를 뒤져(느림) 찾아낸다.
    """
    for c in _cheap_candidates(configured):
        if c and Path(c).is_file():
            return c
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
    for p in comports():
        desc = " ".join(filter(None, [
            getattr(p, "description", "") or "",
            getattr(p, "manufacturer", "") or "",
            getattr(p, "product", "") or "",
            getattr(p, "hwid", "") or "",
        ]))
        out.append({
            "device": p.device,
            "vid": getattr(p, "vid", None),
            "pid": getattr(p, "pid", None),
            "desc": desc,
        })
    return out


def _port_is_pm3(info: dict) -> bool:
    if info.get("vid") and info.get("pid") and (info["vid"], info["pid"]) in _PM3_VIDPID:
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


def detect_device() -> dict:
    """꽂힌 Proxmark3 를 '드라이버 유무까지' 본다.

    1순위: pyserial 로 PM3 의 COM 포트를 찾는다(Proxmark3GUI·ProxSpace 와 같은 검증된 방식).
    COM 포트가 안 보이면(드라이버 없음 등) Windows 는 PnP 전체를 뒤져 '장치는 있는데 COM 이
    없다'(=드라이버 필요)를 가려낸다.
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
    for pat in ("/dev/pm3-*", "/dev/ttyACM*", "/dev/tty.usbmodem*", "/dev/cu.usbmodem*", "/dev/ttyUSB*"):
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[0]
    return None


def _auto_port() -> str | None:
    return detect_port()


def diagnostics() -> dict:
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
    d["device"] = detect_device()
    try:
        d["client"] = find_client(deep=True)
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


def find_firmware_images(client: str) -> dict:
    """클라이언트 근처에서 펌웨어 이미지(fullimage.elf·bootrom.elf)를 찾는다.

    ProxSpace/릴리스 배치: proxmark3.exe 는 보통 client/ 에, .elf 는 armsrc/obj·bootrom/obj
    또는 릴리스면 바로 옆에 있다. 클라이언트 폴더의 위쪽 3단계까지 뒤진다.
    """
    out = {"fullimage": None, "bootrom": None}
    base = Path(client).resolve().parent
    roots = [base] + list(base.parents)[:3]
    for root in roots:
        try:
            for name in ("fullimage.elf", "bootrom.elf"):
                key = "fullimage" if name.startswith("full") else "bootrom"
                if out[key]:
                    continue
                hits = sorted(root.glob("**/" + name))
                if hits:
                    out[key] = str(hits[0])
        except OSError:
            pass
        if out["fullimage"] and out["bootrom"]:
            break
    return out


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
        if port:
            args.extend(["-p", port])
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

    def run_raw(self, extra: list[str], timeout: float = 300) -> Pm3Result:
        """`-c` 없이 클라이언트를 직접 호출한다(플래싱 등: proxmark3 -p <port> --flash ...)."""
        args = [self.client]
        port = self._resolved_port()
        if port:
            args.extend(["-p", port])
        args.extend(extra)
        try:
            done = subprocess.run(
                args, cwd=str(self.workdir) if self.workdir else None,
                capture_output=True, timeout=timeout,
            )
        except FileNotFoundError as e:
            raise DeviceNotFound("pm3 를 실행하지 못했습니다: %s" % e) from None
        except subprocess.TimeoutExpired:
            raise Pm3Error("명령이 %.0f초 안에 끝나지 않았습니다." % timeout) from None
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
