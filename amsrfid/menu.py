"""검은 창에서 번호만 눌러 쓰는 메뉴 (bwbridge 와 같은 결).

run.bat 은 보통 `auto` 로 바로 원터치를 돌리지만, 사람이 골라 쓰고 싶을 때 이 메뉴를 쓴다.
"""
from __future__ import annotations

from pathlib import Path

from . import __version__, update
from .config import Config
from . import workflow
from .pm3 import Pm3, Pm3Error


def _list_bins(cfg: Config) -> list[Path]:
    out = cfg.out_path
    if not out.is_dir():
        return []
    return sorted(out.glob("*.bin"), key=lambda p: p.stat().st_mtime, reverse=True)


def _pick_bin(cfg: Config) -> Path | None:
    bins = _list_bins(cfg)
    if not bins:
        print("저장된 .bin 이 없습니다. 먼저 1번(원터치 읽기)으로 떠 주세요.")
        return None
    print("저장된 덤프:")
    for i, p in enumerate(bins, 1):
        print("  %d) %s" % (i, p.name))
    sel = input("번호를 고르세요 (그냥 Enter 면 취소): ").strip()
    if not sel.isdigit() or not (1 <= int(sel) <= len(bins)):
        return None
    return bins[int(sel) - 1]


def run(cfg: Config | None = None) -> int:
    cfg = cfg or Config.load()
    while True:
        print("")
        print("=" * 52)
        print(" ams-rfid v%s — FM11RF08S 원터치 도구" % __version__)
        print("=" * 52)
        print(" 1) 원터치 읽기 — 꽂고 올리면 키 복구 후 .bin 저장")
        print(" 2) 복제 — 읽은 .bin 을 대상 카드에 쓰기")
        print(" 3) 저장된 .bin 보기")
        print(" 4) 불러오기/조회 — .bin 열어서 블록0·키·값·복제가능 보기")
        print(" 5) 업데이트 확인")
        print(" 6) 드라이버 안내 (Windows, pm3 가 안 잡힐 때)")
        print(" 0) 나가기")
        choice = input("골라 주세요: ").strip()

        try:
            if choice == "1":
                res = workflow.one_touch(cfg, echo=print)
                if res.recovered:
                    print("\n완료 — %s" % res.bin_path)
                else:
                    print("\n덤프를 뜨지 못했습니다. %s" % (res.note or ""))
            elif choice == "2":
                src = _pick_bin(cfg)
                if src is None:
                    print("먼저 원터치로 .bin 을 떠 두거나, out 폴더에 .bin 을 두세요.")
                    continue
                print("\n주의: 대상 카드의 내용을 덮어씁니다. 본인 소유/권한 있는 카드만 쓰세요.")
                if input("계속하려면 y: ").strip().lower() != "y":
                    continue
                pm3 = Pm3.locate(cfg.pm3_path or None, cfg.port or None, cfg.out_path, deep=False)
                workflow.wait_for_device(pm3, cfg, print)
                workflow.clone_to_card(pm3, src, cfg, print)
            elif choice == "3":
                bins = _list_bins(cfg)
                if not bins:
                    print("저장된 .bin 이 없습니다.")
                for p in bins:
                    print("  %s  (%d바이트)" % (p.name, p.stat().st_size))
            elif choice == "4":
                path = input("불러올 .bin 경로(저장된 것은 이름만, 취소는 Enter): ").strip().strip('"')
                if not path:
                    continue
                src = Path(path)
                if not src.is_file():
                    src = cfg.out_path / path          # 이름만 준 경우 out 폴더에서 찾는다
                if not src.is_file():
                    print("파일을 찾지 못했습니다: %s" % path)
                    continue
                try:
                    workflow.analyze_bin(src, print)
                except ValueError as e:
                    print("읽지 못했습니다: %s" % e)
            elif choice == "5":
                update.run(check_only=False, root=cfg.root, echo=print)
            elif choice == "6":
                from .pm3 import install_driver
                ok, msg = install_driver()
                print(msg)
            elif choice == "0":
                return 0
            else:
                print("1~6 또는 0 을 눌러 주세요.")
        except Pm3Error as e:
            print("\n문제가 생겼습니다: %s" % e)
        except KeyboardInterrupt:
            print("\n중단했습니다.")
            return 1
