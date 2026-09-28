#!/usr/bin/env python3
"""Bambu-Lab-RFID-Library 덤프를 앱 에셋(index.json)으로 변환한다.

사용법:
    python3 scripts/build_tag_library.py <라이브러리_경로> <출력_json> [--samples N]

라이브러리 구조: <분류>/<재질>/<색상>/<UID>/hf-mf-<UID>-dump.(bin|json) 또는 *.nfc
색상마다 검증을 통과한 덤프를 최대 N개(기본 6개)까지 담는다.
표준 라이브러리만 사용하므로 별도 패키지 설치가 필요 없다.
"""

import argparse
import base64
import datetime
import hashlib
import hmac
import json
import subprocess
import sys
from pathlib import Path

BLOCK = 16
BLOCKS = 64
DUMP_SIZE = BLOCK * BLOCKS
SALT = bytes.fromhex("9a759cf2c4f7caff222cb9769b41bc96")
CATEGORY_ORDER = ["PLA", "PETG", "ABS", "ASA", "PC", "PA", "TPU", "Support Material"]
# index.json/manifest.json 형식 버전. 앱이 모르는 형식은 내려받지 않는다.
FORMAT_VERSION = 1


def hkdf_keys(uid: bytes, info: bytes) -> list:
    prk = hmac.new(SALT, uid, hashlib.sha256).digest()
    okm, t, counter = b"", b"", 1
    while len(okm) < 6 * 16:
        t = hmac.new(prk, t + info + bytes([counter]), hashlib.sha256).digest()
        okm += t
        counter += 1
    return [okm[i * 6:(i + 1) * 6] for i in range(16)]


def load_dump(path: Path):
    raw = path.read_bytes()
    if path.suffix == ".bin":
        data = raw
    elif path.suffix == ".json":
        blocks = json.loads(raw)["blocks"]
        data = b"".join(
            bytes.fromhex(blocks[str(i)].replace("??", "00")) for i in range(len(blocks))
        )
    elif path.suffix == ".nfc":
        data = b""
        for line in raw.decode(errors="replace").splitlines():
            if line.startswith("Block "):
                data += bytes.fromhex(line.split(":", 1)[1].strip().replace("??", "00").replace(" ", ""))
    else:
        return None
    if len(data) < DUMP_SIZE:
        return None
    return bytearray(data[:DUMP_SIZE])


def validate(dump: bytearray):
    """검증 후 (정상 여부, 사유)를 돌려준다. 트레일러 키가 비어 있으면 UID로 복구한다."""
    b0 = dump[0:16]
    uid = bytes(b0[0:4])
    if b0[0] ^ b0[1] ^ b0[2] ^ b0[3] != b0[4]:
        return False, "BCC 불일치"
    for block in (1, 2, 4, 5):
        if dump[block * 16:(block + 1) * 16] == bytes(16):
            return False, f"블록 {block} 비어 있음"
    signature = b"".join(
        dump[b * 16:(b + 1) * 16] for b in range(40, 64) if b % 4 != 3
    )
    if signature == bytes(len(signature)):
        return False, "RSA 서명 블록 비어 있음"
    keys_a = hkdf_keys(uid, b"RFID-A\x00")
    keys_b = hkdf_keys(uid, b"RFID-B\x00")
    for sector in range(16):
        t = (sector * 4 + 3) * 16
        key_a, access, key_b = dump[t:t + 6], dump[t + 6:t + 10], dump[t + 10:t + 16]
        if key_a in (bytes(6), b"\xff" * 6):
            dump[t:t + 6] = keys_a[sector]
        elif key_a != keys_a[sector]:
            return False, f"섹터 {sector} KeyA 불일치"
        if key_b in (bytes(6), b"\xff" * 6):
            dump[t + 10:t + 16] = keys_b[sector]
        elif key_b != keys_b[sector]:
            return False, f"섹터 {sector} KeyB 불일치"
        if access == bytes(4):
            dump[t + 6:t + 10] = bytes.fromhex("87878769")
    return True, ""


def _le16(b, off):
    return b[off] | (b[off + 1] << 8)


def _ascii(b):
    return b.decode("ascii", "replace").replace("\x00", " ").strip()


def display_info(dump: bytearray) -> dict:
    """첫 샘플에서 UI 표시용 필드를 뽑는다(색상 스와치·요약)."""
    import struct

    def blk(i):
        return dump[i * 16:(i + 1) * 16]

    b5, b6, b16 = blk(5), blk(6), blk(16)
    color = "#" + b5[0:4].hex().upper()
    second = None
    if b16[0] == 0x02 and b16[1] == 0x00 and _le16(b16, 2) == 2:
        second = "#" + bytes([b16[7], b16[6], b16[5], b16[4]]).hex().upper()
    return {
        "colorHex": color,
        "color2": second,
        "type": _ascii(blk(2)),
        "detailType": _ascii(blk(4)),
        "weight": _le16(b5, 4),
        "diameter": round(struct.unpack("<f", bytes(b5[8:12]))[0], 2),
        "tmin": _le16(b6, 10),
        "tmax": _le16(b6, 8),
        "bed": _le16(b6, 6),
    }


def find_dump_file(tag_dir: Path):
    for pattern in ("*-dump.bin", "*-dump.json", "*.nfc"):
        found = sorted(tag_dir.glob(pattern))
        if found:
            return found[0]
    return None


def git_commit(repo: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
        ).strip()
    except Exception:
        return ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("library", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--samples", type=int, default=6)
    parser.add_argument("--manifest", type=Path, help="앱 업데이트 확인용 manifest.json 출력 경로")
    args = parser.parse_args()

    entries = []
    rejected = 0
    for category_dir in sorted(p for p in args.library.iterdir() if p.is_dir() and not p.name.startswith(".")):
        for material_dir in sorted(p for p in category_dir.iterdir() if p.is_dir()):
            for color_dir in sorted(p for p in material_dir.iterdir() if p.is_dir()):
                samples = []
                for tag_dir in sorted(p for p in color_dir.iterdir() if p.is_dir()):
                    if len(samples) >= args.samples:
                        break
                    dump_file = find_dump_file(tag_dir)
                    if dump_file is None:
                        continue
                    try:
                        dump = load_dump(dump_file)
                    except Exception as error:  # 손상된 파일은 건너뛴다
                        print(f"skip {dump_file}: {error}", file=sys.stderr)
                        dump = None
                    if dump is None:
                        rejected += 1
                        continue
                    ok, reason = validate(dump)
                    if not ok:
                        rejected += 1
                        print(f"skip {dump_file}: {reason}", file=sys.stderr)
                        continue
                    samples.append({
                        "uid": dump[0:4].hex().upper(),
                        "dump": base64.b64encode(bytes(dump)).decode(),
                    })
                if samples:
                    first = base64.b64decode(samples[0]["dump"])
                    entries.append({
                        "category": category_dir.name,
                        "material": material_dir.name,
                        "color": color_dir.name,
                        "info": display_info(bytearray(first)),
                        "samples": samples,
                    })

    def sort_key(entry):
        category = entry["category"]
        order = CATEGORY_ORDER.index(category) if category in CATEGORY_ORDER else len(CATEGORY_ORDER)
        return (order, category, entry["material"], entry["color"])

    entries.sort(key=sort_key)
    commit = git_commit(args.library)
    generated = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    # 앱은 파일 앞부분에서 commit/generated 를 빠르게 읽으므로 entries 보다 먼저 둔다.
    payload = {
        "source": "https://github.com/queengooborg/Bambu-Lab-RFID-Library",
        "format": FORMAT_VERSION,
        "commit": commit,
        "generated": generated,
        "entries": entries,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    sample_count = sum(len(e["samples"]) for e in entries)
    print(f"{len(entries)} colors, {sample_count} samples, {rejected} rejected -> {args.output}")

    if args.manifest:
        # 앱이 업데이트 여부와 추가/삭제된 색상을 index.json 을 받기 전에 알 수 있도록 하는 요약.
        manifest = {
            "format": FORMAT_VERSION,
            "commit": commit,
            "generated": generated,
            "colors": len(entries),
            "samples": sample_count,
            "keys": [f"{e['category']}/{e['material']}/{e['color']}" for e in entries],
        }
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(json.dumps(manifest, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"manifest -> {args.manifest}")
    return 0 if entries else 1


if __name__ == "__main__":
    sys.exit(main())
