"""명령줄 진입점.

  python -m amsrfid            → 메뉴
  python -m amsrfid ui         → 브라우저로 쓰는 로컬 웹 UI (run.bat 기본)
  python -m amsrfid auto       → 원터치(장치/카드 대기 → 키 복구 → .bin 저장)
  python -m amsrfid clone      → 원터치로 읽은 뒤 대상 카드에 복제
  python -m amsrfid clone --from out/ams-....bin  → 그 파일을 대상 카드에 복제
  python -m amsrfid info       → 카드 종류만 확인
  python -m amsrfid update [--check]
  python -m amsrfid version
"""
from __future__ import annotations

import argparse
import sys

from . import __version__, update, workflow
from .config import Config
from .pm3 import Pm3, Pm3Error


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="amsrfid", description="Proxmark3 FM11RF08S 원터치 도구")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("menu", help="대화형 메뉴")
    sub.add_parser("auto", help="원터치: 꽂고 올리면 키 복구 후 .bin 저장")

    pw = sub.add_parser("ui", help="브라우저로 쓰는 로컬 웹 UI")
    pw.add_argument("--port", type=int, default=8724, help="포트(기본 8724)")
    pw.add_argument("--no-browser", action="store_true", help="브라우저를 자동으로 열지 않음")

    pc = sub.add_parser("clone", help="대상 카드에 복제(쓰기)")
    pc.add_argument("--from", dest="src", default=None, help="쓸 .bin 파일(없으면 먼저 원터치로 읽음)")

    sub.add_parser("info", help="카드 종류만 확인")

    pu = sub.add_parser("update", help="배포 브랜치에서 최신본 받기")
    pu.add_argument("--check", action="store_true", help="새 버전이 있는지만 확인")

    sub.add_parser("version", help="버전 출력")
    return p


def cmd_auto(cfg: Config) -> int:
    res = workflow.one_touch(cfg, echo=print)
    if res.recovered:
        print("\n완료 — 덤프: %s" % res.bin_path)
        return 0
    print("\n덤프를 뜨지 못했습니다. %s" % (res.note or ""))
    return 1


def cmd_clone(cfg: Config, src: str | None) -> int:
    pm3 = Pm3.locate(cfg.pm3_path or None, cfg.port or None, cfg.out_path)
    workflow.wait_for_device(pm3, cfg, print)
    if src is None:
        workflow.wait_for_card(pm3, cfg, print)
        info = workflow.identify(pm3, print)
        res = workflow.recover_and_dump(pm3, info, cfg, print)
        if not res.recovered:
            print("\n먼저 읽기에 실패했습니다. 복제를 멈춥니다. %s" % (res.note or ""))
            return 1
        src = str(res.bin_path)
        print("\n이제 대상(쓸) 카드로 바꿔 올려 주세요.")
    print("\n주의: 대상 카드를 덮어씁니다. 본인 소유/권한 있는 카드만 쓰세요.")
    workflow.clone_to_card(pm3, src, cfg, print)
    return 0


def cmd_info(cfg: Config) -> int:
    pm3 = Pm3.locate(cfg.pm3_path or None, cfg.port or None, cfg.out_path)
    workflow.wait_for_device(pm3, cfg, print)
    workflow.wait_for_card(pm3, cfg, print)
    info = workflow.identify(pm3, print)
    print(info.summary)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = Config.load()

    cmd = args.cmd
    try:
        if cmd in (None, "menu"):
            from . import menu
            return menu.run(cfg)
        if cmd == "auto":
            return cmd_auto(cfg)
        if cmd == "ui":
            from . import web
            return web.serve(cfg, port=args.port, open_browser=not args.no_browser)
        if cmd == "clone":
            return cmd_clone(cfg, args.src)
        if cmd == "info":
            return cmd_info(cfg)
        if cmd == "update":
            return update.run(check_only=args.check, root=cfg.root, echo=print)
        if cmd == "version":
            print("ams-rfid v%s" % __version__)
            return 0
    except Pm3Error as e:
        print("문제가 생겼습니다: %s" % e, file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\n중단했습니다.", file=sys.stderr)
        return 130
    return 0
