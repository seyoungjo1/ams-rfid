"""amsrfid.toml 설정 읽기 (bwbridge 와 같은 방식 — 폴더에 두면 자동으로 읽는다).

설정이 없어도 전부 기본값으로 돈다. 바꾸고 싶은 것만 적으면 된다.

    # amsrfid.toml 예시
    pm3_path = "C:\\ProxSpace\\pm3\\pm3.bat"   # 비우면 알아서 찾는다
    port     = ""                               # 날것 proxmark3 쓸 때만
    outdir   = "out"                            # 덤프(.bin) 저장 폴더
    timeout  = 300                              # 키 복구 같은 긴 명령의 제한 시간(초)
    poll     = 1.5                              # 장치/카드 기다릴 때 다시 볼 간격(초)
    wait     = 120                              # 장치/카드를 최대 몇 초 기다릴지
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

try:                                     # 3.11+ 표준, 아니면 tomli(있으면)
    import tomllib as _toml
except ModuleNotFoundError:              # pragma: no cover
    try:
        import tomli as _toml            # type: ignore
    except ModuleNotFoundError:
        _toml = None                     # type: ignore

ROOT = Path(__file__).resolve().parent.parent
CONFIG_NAMES = ("amsrfid.toml", "ams-rfid.toml")


class ConfigError(ValueError):
    pass


@dataclass
class Config:
    use_system_client: bool = False
    pm3_path: str = ""
    port: str = ""
    outdir: str = "out"
    timeout: float = 300.0
    poll: float = 1.5
    wait: float = 120.0
    root: Path = ROOT

    @property
    def out_path(self) -> Path:
        p = Path(self.outdir)
        if not p.is_absolute():
            p = self.root / p
        return p

    @classmethod
    def load(cls, root: Path | None = None) -> "Config":
        root = root or ROOT
        data: dict = {}
        if _toml is not None:
            for name in CONFIG_NAMES:
                p = root / name
                if p.is_file():
                    try:
                        data = _toml.loads(p.read_text(encoding="utf-8-sig"))
                    except (OSError, ValueError) as e:
                        raise ConfigError("설정 파일 %s 를 읽지 못했습니다: %s. Windows 경로는 작은따옴표로 감싸세요." % (p, e)) from None
                    break
        numbers = {}
        for key, default in (("timeout", 300), ("poll", 1.5), ("wait", 120)):
            try:
                value = float(data.get(key, default))
            except (TypeError, ValueError):
                raise ConfigError("%s 는 양수여야 합니다." % key) from None
            if not math.isfinite(value) or value <= 0:
                raise ConfigError("%s 는 유한한 양수여야 합니다." % key)
            numbers[key] = value
        return cls(
            use_system_client=data.get("use_system_client") is True,
            pm3_path=str(data.get("pm3_path", "") or ""),
            port=str(data.get("port", "") or ""),
            outdir=str(data.get("outdir", "out") or "out"),
            timeout=numbers["timeout"],
            poll=numbers["poll"],
            wait=numbers["wait"],
            root=root,
        )
