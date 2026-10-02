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
    from .pm3 import detect_device
    echo("Proxmark3 를 찾는 중… (USB 에 꽂아 주세요)")
    deadline = time.monotonic() + cfg.wait
    first = True
    while True:
        if pm3.device_present():
            echo("  → Proxmark3 연결 확인")
            return
        # 장치는 보이는데 COM 포트가 없으면(=드라이버 없음) 바로 알려 준다.
        dev = detect_device()
        if dev.get("needs_driver"):
            raise DeviceNotFound(
                "Proxmark3 장치는 보이는데 드라이버가 없어 COM 포트가 안 잡힙니다"
                "%s.\n'드라이버 설치'(웹 UI 버튼 또는 `python -m amsrfid driver`)를 먼저 실행하세요."
                % (" (" + dev.get("name", "") + ")" if dev.get("name") else "")
            )
        if time.monotonic() > deadline:
            raise DeviceNotFound(
                "제한 시간(%.0f초) 안에 Proxmark3 를 찾지 못했습니다. "
                "USB 케이블·포트를 확인하거나, 드라이버를 설치해 보세요." % cfg.wait
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
    """전 섹터 키를 복구하고 덤프를 저장한다.

    FM11RF08S 는 정적 암호화 nonce 대응 때문에 일반 nested/autopwn 으로는 안 풀린다.
    Proxmark3 Iceman 의 전용 스크립트 `fm11rf08s_recovery` 를 쓴다. 이 스크립트는
    백도어 키로 섹터별 nonce 를 모으고(`hf mf isen --collect_fm11rf08s_with_data`),
    staticnested_2x1nt_rf08s 솔버로 KeyA/KeyB 를 복구한 뒤 키 파일·덤프를 떨군다.
    일반 MIFARE Classic 은 기존대로 autopwn 을 쓴다.
    """
    out = cfg.out_path
    out.mkdir(parents=True, exist_ok=True)
    pm3.workdir = out                           # pm3 가 덤프를 이 폴더에 떨구게 한다

    # pm3 의 지난 임시 산출물(hf-mf-*)을 먼저 치운다 — 이번 결과만 남게. 보관본은 ams-*.bin 이라 안전.
    for stale in list(out.glob("hf-mf-*-dump.bin")) + list(out.glob("hf-mf-*-key.bin")):
        try:
            stale.unlink()
        except OSError:
            pass

    started = time.time()
    if info.is_fm11rf08s:
        echo("FM11RF08S — 전용 복구 스크립트로 키를 복구합니다 (백도어 %s, static nested)."
             % D.FM11RF08S_BACKDOOR)
        echo("  카드를 안테나 위에 그대로 두세요. 수 분 걸릴 수 있습니다…")
        # -x: 먼저 기본키 확인(fchk)  -y: 끝에 찾은 키로 재확인하며 덤프 저장
        pm3.run("script run fm11rf08s_recovery -x -y", timeout=cfg.timeout)
    else:
        echo("일반 MIFARE Classic — autopwn 으로 키를 복구합니다. 수 분 걸릴 수 있습니다…")
        pm3.run("hf mf autopwn", timeout=cfg.timeout)

    binp = _newest_match(out, "hf-mf-*-dump.bin", info.uid, started)
    keyp = _newest_match(out, "hf-mf-*-key.bin", info.uid, started)

    # 키는 나왔는데 덤프가 없으면, 그 키 파일로 덤프를 한 번 더 뜬다.
    if not binp and keyp:
        echo("  복구한 키로 덤프를 뜹니다…")
        pm3.run("hf mf dump", timeout=cfg.timeout)
        binp = _newest_match(out, "hf-mf-*-dump.bin", info.uid, started)

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
            echo(D.Dump.load(final).report())
        except ValueError:
            pass
        return result

    result.note = (
        "키/덤프를 얻지 못했습니다. 카드가 안테나 위에 그대로 있는지, 접촉이 좋은지 확인하세요. "
        "FM11RF08S 가 맞는데도 실패하면 pm3 셸에서 직접 `script run fm11rf08s_recovery -x -y` 를 "
        "돌려 메시지를 확인하세요(펌웨어가 최신이어야 백도어 복구가 됩니다)."
    )
    echo("  → " + result.note)
    return result


def analyze_bin(path: str | Path, echo: Echo = print) -> dict:
    """불러온 .bin 하나를 뜯어보고(블록0·키·값·복제가능) 리포트를 출력한다."""
    d = D.Dump.load(path)
    report = d.report()
    echo(report)
    return d.analyze()


# -- 복제(쓰기) -------------------------------------------------------------


def _is_gen1a(magic: str) -> bool:
    m = (magic or "").lower()
    return "gen1" in m or "gen 1" in m


def _resolve_key_file(key_path, uid: str, out: Path, d: "D.Dump", echo: Echo) -> Path | None:
    """restore 에 넘길 키 파일을 고른다.

    우선순위: 직접 준 key_path > out/hf-mf-<UID>-key.bin(복구 결과) > 덤프 트레일러에서 생성.
    덤프 트레일러가 FF 껍데기면 생성해도 소용없다(앞 단계에서 걸러진다).
    """
    if key_path and Path(key_path).is_file():
        echo("  키 파일: %s" % Path(key_path).name)
        return Path(key_path)
    cand = out / ("hf-mf-%s-key.bin" % uid)
    if cand.is_file():
        echo("  복구된 키 파일 사용: %s" % cand.name)
        return cand
    gen = d.write_key_file(out / ("hf-mf-%s-key.bin" % uid))
    echo("  덤프 트레일러에서 키 파일 생성: %s" % gen.name)
    return gen


def clone_to_card(pm3: Pm3, bin_path: str | Path, cfg: Config, echo: Echo = print,
                  key_path: str | Path | None = None, allow_placeholder: bool = False) -> None:
    """떠 둔 .bin 을 대상 카드에 쓴다(복제). 대상 카드를 덮어쓰므로 조심.

    복제의 핵심(백도어 함정)
      · 백도어로 데이터만 읽은 덤프는 트레일러 키가 FF '껍데기'다 — 그대로 복제하면 원본
        키가 안 들어간다. 그런 덤프는 막고, 먼저 백도어 복구(fm11rf08s_recovery)로 진짜
        키가 담긴 덤프/키 파일을 받으라고 안내한다.
    방식
      · gen1a 매직카드 → `hf mf cload` : 블록0(UID·서명)까지 통째로, 인증 없이 쓴다(가장 확실).
      · 그 외/일반     → `hf mf restore` : 키 파일로 대상을 인증해 데이터·키를 쓴다(일반 카드는
        블록0=UID 변경 불가).
    """
    bin_path = Path(bin_path)
    if not bin_path.is_file():
        raise WorkflowError("덤프 파일을 찾을 수 없습니다: %s" % bin_path)
    d = D.Dump.load(bin_path)
    a = d.analyze()
    uid = a["uid"]

    # 껍데기 키 가드
    if a["has_placeholder_keys"] and key_path is None and not allow_placeholder:
        raise WorkflowError(
            "이 덤프는 섹터 %s 의 KeyA 가 FF 껍데기입니다(데이터는 있는데 진짜 키가 가려짐).\n"
            "이 상태로 복제하면 원본 키가 복제되지 않습니다. 먼저 백도어 복구로 진짜 키가 담긴\n"
            "덤프/키 파일(hf-mf-%s-key.bin)을 받으세요(원터치 읽기가 이 과정을 합니다).\n"
            "데이터만이라도 gen1a 매직에 통째로 쓰려면 allow_placeholder 로 진행할 수 있습니다."
            % (a["placeholder_sectors"], uid))

    echo("대상(쓸) 카드를 올려 주세요…")
    wait_for_card(pm3, cfg, echo)
    info = identify(pm3, echo)
    pm3.workdir = cfg.out_path

    if _is_gen1a(info.magic):
        echo("gen1a 매직카드 — cload 로 블록0(UID %s·서명)까지 통째로 씁니다." % uid)
        res = pm3.run('hf mf cload -f "%s"' % bin_path, timeout=cfg.timeout)
    else:
        kf = _resolve_key_file(key_path, uid, cfg.out_path, d, echo)
        cmd = 'hf mf restore --1k -f "%s"' % bin_path
        if kf:
            cmd += ' -k "%s"' % kf
        if uid:
            cmd += ' --uid %s' % uid
        if info.magic:
            echo("매직카드(%s) — restore 로 씁니다(블록0 포함 가능할 수 있음)." % info.magic)
        else:
            echo("일반 카드 — restore 로 데이터·키를 씁니다(블록0=UID 는 보통 불가).")
        res = pm3.run(cmd, timeout=cfg.timeout)

    low = res.text.lower()
    if ("fail" in low or "error" in low or "can't" in low) and "wrote" not in low and "ok" not in low:
        raise WorkflowError("쓰기에 실패했을 수 있습니다. pm3 출력 확인:\n" + res.text[-700:])
    echo("복제 시도 완료 — %s 를 대상 카드에 썼습니다. (hf mf dump 로 되읽어 검증을 권장)" % bin_path.name)


# -- 전체 원터치 ------------------------------------------------------------


def one_touch(cfg: Config, echo: Echo = print) -> OneTouchResult:
    """꽂은 상태에서 호출 — 장치/카드 대기부터 덤프 저장까지 한 번에."""
    pm3 = Pm3.locate(
        configured=cfg.pm3_path or None,
        port=cfg.port or None,
        workdir=cfg.out_path,
        deep=True,                      # 흔한 위치에 없으면 드라이브에서 찾아낸다(자동)
    )
    echo("pm3 클라이언트: %s" % pm3.client)
    wait_for_device(pm3, cfg, echo)
    wait_for_card(pm3, cfg, echo)
    info = identify(pm3, echo)
    return recover_and_dump(pm3, info, cfg, echo)
