"""원터치 흐름: 꽂으면 → 장치 찾기 → 카드 찾기 → 종류 확인 → 키 복구 → .bin 저장.

Proxmark3 에 아무것도 없는 상태에서 run.bat 을 누르면 여기까지 저절로 진행된다.
복제(쓰기)는 대상 카드를 망가뜨릴 수 있어 따로 떼어 두었다(clone_to_card).

키 복구는 Proxmark3 Iceman 의 `hf mf autopwn` 에 맡긴다. FM11RF08S 는 공개된 백도어
키를 autopwn 이 알아서 활용해 전 섹터 키를 복구하고 덤프까지 떨군다. autopwn 이 못 풀면
전용 복구 스크립트(fm11rf08s_recovery)를 안내한다.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from . import dump as D
from .config import Config
from .pm3 import Pm3, Pm3Error, DeviceNotFound

Echo = Callable[[str], Any]


class WorkflowError(Pm3Error):
    pass


@dataclass
class OneTouchResult:
    info: D.CardInfo
    bin_path: Path | None = None
    key_path: Path | None = None
    recovered: bool = False
    note: str = ""


# -- 기다리기 ---------------------------------------------------------------


def wait_for_device(pm3: Pm3, cfg: Config, echo: Echo = print) -> None:
    echo("Proxmark3 를 찾는 중… (USB 에 꽂아 주세요)")
    deadline = time.monotonic() + cfg.wait
    first = True
    while True:
        if pm3.device_present():
            echo("  → Proxmark3 연결 확인")
            return
        if time.monotonic() > deadline:
            raise DeviceNotFound(
                "제한 시간(%.0f초) 안에 Proxmark3 를 찾지 못했습니다. "
                "케이블·드라이버를 확인하세요." % cfg.wait
            )
        if first:
            echo("  (아직 안 보입니다 — 꽂을 때까지 기다립니다)")
            first = False
        time.sleep(cfg.poll)


def wait_for_card(pm3: Pm3, cfg: Config, echo: Echo = print) -> None:
    echo("카드를 안테나 위에 올려 주세요…")
    deadline = time.monotonic() + cfg.wait
    while True:
        if pm3.card_present():
            echo("  → 카드 감지")
            return
        if time.monotonic() > deadline:
            raise WorkflowError(
                "제한 시간(%.0f초) 안에 카드를 찾지 못했습니다. 안테나 위에 올렸는지 확인하세요."
                % cfg.wait
            )
        time.sleep(cfg.poll)


# -- 확인 -------------------------------------------------------------------


def identify(pm3: Pm3, echo: Echo = print) -> D.CardInfo:
    echo("카드 종류를 확인하는 중…")
    r14 = pm3.run("hf 14a info", timeout=30)
    info = D.parse_14a_info(r14.text)
    rmf = pm3.run("hf mf info", timeout=60)
    D.parse_mf_info(rmf.text, into=info)
    echo("  → %s" % info.summary)
    if not info.is_fm11rf08s:
        echo("  (주의: FM11RF08S 로 보이지 않습니다. 그래도 MIFARE Classic 1K 호환이면 진행합니다.)")
    return info


# -- 키 복구 + 덤프 ---------------------------------------------------------


def _newest_match(outdir: Path, pattern: str, uid: str, since: float) -> Path | None:
    """pm3 가 **이번 실행에서** 떨군 파일만 고른다(since 이후 수정된 것).

    since 로 거르지 않으면, autopwn 이 이번엔 실패해도 폴더에 남아 있던 지난 덤프를
    성공으로 착각한다. 이번에 새로 생긴 것만 받아들인다.
    """
    outdir.mkdir(parents=True, exist_ok=True)
    cands = [p for p in outdir.glob(pattern) if p.stat().st_mtime >= since - 1]
    cands.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    if uid:
        for p in cands:
            if uid.lower() in p.name.lower():
                return p
    return cands[0] if cands else None


def recover_and_dump(
    pm3: Pm3, info: D.CardInfo, cfg: Config, echo: Echo = print
) -> OneTouchResult:
    """autopwn 으로 전 섹터 키를 복구하고 덤프를 저장한다."""
    out = cfg.out_path
    out.mkdir(parents=True, exist_ok=True)
    pm3.workdir = out                           # pm3 가 덤프를 이 폴더에 떨구게 한다

    # pm3 의 지난 임시 산출물(hf-mf-*)을 먼저 치운다 — 이번 결과만 남게. 보관본은 ams-*.bin 이라 안전.
    for stale in list(out.glob("hf-mf-*-dump.bin")) + list(out.glob("hf-mf-*-key.bin")):
        try:
            stale.unlink()
        except OSError:
            pass

    echo("키를 복구하고 덤프를 뜨는 중… (수 분 걸릴 수 있습니다)")
    started = time.time()
    res = pm3.run("hf mf autopwn", timeout=cfg.timeout)
    low = res.text.lower()

    binp = _newest_match(out, "hf-mf-*-dump.bin", info.uid, started)
    keyp = _newest_match(out, "hf-mf-*-key.bin", info.uid, started)

    result = OneTouchResult(info=info)
    if binp and binp.is_file():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        tag = info.uid or "card"
        final = out / ("ams-%s-%s.bin" % (tag, stamp))
        final.write_bytes(binp.read_bytes())
        result.bin_path = final
        result.key_path = keyp if (keyp and keyp.is_file()) else None
        result.recovered = True
        echo("  → 덤프 저장: %s" % final)
        try:
            echo(D.Dump.load(final).pretty())
        except ValueError:
            pass
        return result

    # autopwn 이 덤프를 못 남긴 경우 — FM11RF08S 전용 복구 스크립트를 안내한다.
    if info.is_fm11rf08s and ("fail" in low or "fm11rf08s" in low or not binp):
        result.note = (
            "autopwn 이 전 섹터를 풀지 못했습니다. FM11RF08S 전용 복구 스크립트로 다시 시도하세요:\n"
            "  pm3 셸에서:  script run fm11rf08s_recovery\n"
            "  (복구된 키 파일로 `hf mf dump` 하면 .bin 이 나옵니다. 백도어 키 %s 를 씁니다.)"
            % D.FM11RF08S_BACKDOOR
        )
        echo("  → " + result.note)
    else:
        result.note = "키 복구에 실패했습니다. 카드가 안테나 위에 그대로 있는지, 접촉이 좋은지 확인하세요."
        echo("  → " + result.note)
    return result


# -- 복제(쓰기) -------------------------------------------------------------


def clone_to_card(pm3: Pm3, bin_path: str | Path, cfg: Config, echo: Echo = print) -> None:
    """떠 둔 .bin 을 대상 카드에 쓴다(복제). 대상 카드를 덮어쓰므로 조심.

    · 매직 카드(gen1a 등): `hf mf cload` — 블록 0 까지 통째로 쓴다.
    · 일반/FM11RF08S: `hf mf restore` — 덤프 안 트레일러의 키로 블록을 되쓴다.
    """
    bin_path = Path(bin_path)
    if not bin_path.is_file():
        raise WorkflowError("덤프 파일을 찾을 수 없습니다: %s" % bin_path)
    d = D.Dump.load(bin_path)

    echo("대상(쓸) 카드를 올려 주세요…")
    wait_for_card(pm3, cfg, echo)
    info = identify(pm3, echo)

    pm3.workdir = cfg.out_path
    if info.magic and ("gen1" in info.magic.lower() or "gen 1" in info.magic.lower()):
        echo("매직(gen1a) 카드로 판단 — cload 로 통째로 씁니다.")
        res = pm3.run('hf mf cload -f "%s"' % bin_path, timeout=cfg.timeout)
    elif info.magic:
        echo("매직 카드(%s) — restore 로 씁니다." % info.magic)
        res = pm3.run('hf mf restore -f "%s" --force' % bin_path, timeout=cfg.timeout)
    else:
        echo("일반 카드 — 덤프의 키로 restore 를 시도합니다(블록 0 은 보통 못 바꿉니다).")
        res = pm3.run('hf mf restore -f "%s"' % bin_path, timeout=cfg.timeout)

    if "fail" in res.text.lower() and "wrote" not in res.text.lower():
        raise WorkflowError("쓰기에 실패했습니다. 카드 종류/키를 확인하세요.\n" + res.text[-600:])
    echo("복제 완료 — 대상 카드에 %s 를 썼습니다." % bin_path.name)


# -- 전체 원터치 ------------------------------------------------------------


def one_touch(cfg: Config, echo: Echo = print) -> OneTouchResult:
    """꽂은 상태에서 호출 — 장치/카드 대기부터 덤프 저장까지 한 번에."""
    pm3 = Pm3.locate(
        configured=cfg.pm3_path or None,
        port=cfg.port or None,
        workdir=cfg.out_path,
    )
    echo("pm3 클라이언트: %s" % pm3.client)
    wait_for_device(pm3, cfg, echo)
    wait_for_card(pm3, cfg, echo)
    info = identify(pm3, echo)
    return recover_and_dump(pm3, info, cfg, echo)
