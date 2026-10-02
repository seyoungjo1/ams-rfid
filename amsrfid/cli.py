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
import shutil
import sys
from pathlib import Path

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
    pc.add_argument("--key", dest="key", default=None, help="대상 인증에 쓸 키 파일(hf-mf-<UID>-key.bin)")
    pc.add_argument("--force-placeholder", action="store_true",
                    help="키가 FF 껍데기인 덤프라도 그대로 진행(gen1a 매직에 데이터만 통째로)")

    pa = sub.add_parser("analyze", help="저장된/불러온 .bin 을 조회(블록0·키·값·복제가능)")
    pa.add_argument("file", help="조회할 .bin 경로")

    pi = sub.add_parser("import", help="외부 .bin 을 out 폴더로 불러오기(+조회)")
    pi.add_argument("file", help="불러올 .bin 경로")

    pd = sub.add_parser("driver", help="Proxmark3 드라이버 설치(Windows, 공식 proxmark3.inf)")
    pd.add_argument("--if-needed", action="store_true",
                    help="장치는 보이는데 드라이버가 없을 때만 설치(조용히 통과)")

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


def cmd_clone(cfg: Config, src: str | None, key: str | None = None,
              force_placeholder: bool = False) -> int:
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
        key = key or (str(res.key_path) if res.key_path else None)
        print("\n이제 대상(쓸) 카드로 바꿔 올려 주세요.")
    print("\n주의: 대상 카드를 덮어씁니다. 본인 소유/권한 있는 카드만 쓰세요.")
    workflow.clone_to_card(pm3, src, cfg, print, key_path=key, allow_placeholder=force_placeholder)
    return 0


def cmd_analyze(cfg: Config, file: str) -> int:
    workflow.analyze_bin(file, print)
    return 0


def cmd_driver(cfg: Config, if_needed: bool) -> int:
    from .pm3 import detect_device, install_driver
    if if_needed:
        dev = detect_device()
        if not (dev.get("present") and dev.get("needs_driver")):
            return 0                         # 설치 불필요 — 조용히 통과
        print("Proxmark3 장치가 보이는데 드라이버가 없습니다 — 설치를 시작합니다(관리자 권한).")
    ok, msg = install_driver()
    print(msg)
    return 0 if ok else 1


def cmd_import(cfg: Config, file: str) -> int:
    from . import dump as D
    src = Path(file)
    try:
        D.Dump.load(src)                       # 크기/형식 먼저 확인
    except ValueError as e:
        print("불러오지 못했습니다: %s" % e)
        return 1
    cfg.out_path.mkdir(parents=True, exist_ok=True)
    dest = cfg.out_path / src.name
    if src.resolve() != dest.resolve():
        shutil.copyfile(src, dest)
    print("불러왔습니다: %s" % dest)
    workflow.analyze_bin(dest, print)
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
            return cmd_clone(cfg, args.src, key=args.key, force_placeholder=args.force_placeholder)
        if cmd == "analyze":
            return cmd_analyze(cfg, args.file)
        if cmd == "import":
            return cmd_import(cfg, args.file)
        if cmd == "driver":
            return cmd_driver(cfg, args.if_needed)
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
