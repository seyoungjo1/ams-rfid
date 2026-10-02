"""MIFARE Classic 1K 덤프(.bin)와 pm3 출력 파싱.

FM11RF08S 는 MIFARE Classic 1K 호환이다:
  · 16 섹터 × 4 블록 × 16 바이트 = 1024 바이트
  · 각 섹터의 마지막 블록 = 섹터 트레일러: KeyA(6) · 액세스비트(3) · GPB(1) · KeyB(6)
  · 블록 0 = 제조사 블록(UID 등), 보통 읽기 전용
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

BLOCK = 16          # 바이트
BLOCKS_PER_SECTOR = 4
SECTORS = 16
BLOCKS = SECTORS * BLOCKS_PER_SECTOR        # 64
SIZE_1K = BLOCKS * BLOCK                      # 1024

# FM11RF08* 계열의 공개된 백도어 키(Fudan, 2024 Teuwen 연구). pm3 가 키 복구에 쓴다.
#   FM11RF08S → A396EFA4E24F · FM11RF08 → A31667A8CEC1 · FM11RF32N → 518B3354E760
FM11RF08S_BACKDOOR = "A396EFA4E24F"
BACKDOORS = {"FM11RF08S": "A396EFA4E24F", "FM11RF08": "A31667A8CEC1", "FM11RF32N": "518B3354E760"}

# 널리 쓰이는 기본/출고 키 — "사용자가 바꾼 키"인지 가르는 데 쓴다.
DEFAULT_KEYS = {
    "FFFFFFFFFFFF", "000000000000", "A0A1A2A3A4A5", "D3F7D3F7D3F7",
    "A0B0C0D0E0F0", "B0B1B2B3B4B5", "4D3A99C351DD", "1A982C7E459A",
    "AABBCCDDEEFF", "714C5C886E97", "587EE5F9350F", "A0478CC39091",
    "533CB6C723F6", "8FD0A4F256E9",
}


def is_default_key(k: str) -> bool:
    return (k or "").upper() in DEFAULT_KEYS


def sector_of(block: int) -> int:
    return block // BLOCKS_PER_SECTOR


def is_trailer(block: int) -> bool:
    return block % BLOCKS_PER_SECTOR == BLOCKS_PER_SECTOR - 1


def trailer_block(sector: int) -> int:
    return sector * BLOCKS_PER_SECTOR + (BLOCKS_PER_SECTOR - 1)


@dataclass
class CardInfo:
    uid: str = ""
    atqa: str = ""
    sak: str = ""
    is_fm11rf08s: bool = False
    backdoor: bool = False
    magic: str = ""          # 매직 카드 종류(gen1a/gen2/gen4 …) 또는 빈 문자열
    raw: str = ""

    @property
    def summary(self) -> str:
        bits = ["UID %s" % (self.uid or "?")]
        if self.sak:
            bits.append("SAK %s" % self.sak)
        if self.atqa:
            bits.append("ATQA %s" % self.atqa)
        if self.is_fm11rf08s:
            bits.append("FM11RF08S")
        if self.backdoor:
            bits.append("백도어 키 사용 가능")
        if self.magic:
            bits.append("매직: %s" % self.magic)
        return " · ".join(bits)


_UID = re.compile(r"UID\s*:?\s*((?:[0-9A-Fa-f]{2}[ ]?){4,10})")
_ATQA = re.compile(r"ATQA\s*:?\s*([0-9A-Fa-f]{2}[ ]?[0-9A-Fa-f]{2})")
_SAK = re.compile(r"SAK\s*:?\s*([0-9A-Fa-f]{2})")


def _norm_hex(s: str) -> str:
    return re.sub(r"\s+", "", s or "").upper()


def parse_14a_info(text: str) -> CardInfo:
    info = CardInfo(raw=text)
    m = _UID.search(text)
    if m:
        info.uid = _norm_hex(m.group(1))
    m = _ATQA.search(text)
    if m:
        info.atqa = _norm_hex(m.group(1))
    m = _SAK.search(text)
    if m:
        info.sak = _norm_hex(m.group(1))
    return info


def parse_mf_info(text: str, into: CardInfo | None = None) -> CardInfo:
    """`hf mf info` 출력에서 FM11RF08S·백도어·매직 여부를 읽는다."""
    info = into or CardInfo(raw=text)
    low = text.lower()
    if "fm11rf08s" in low or "fudan fm11rf08s" in low:
        info.is_fm11rf08s = True
    if "backdoor" in low:
        # "Backdoor ... enabled/present/found" 처럼 긍정 문맥일 때만.
        if re.search(r"backdoor[^\n]*(present|found|enabled|yes|supported|usable|open)", low):
            info.backdoor = True
    m = re.search(r"magic capabilities\s*\.*\s*([^\n]+)", low)
    if m:
        cap = m.group(1).strip()
        if cap and "n/a" not in cap and "no" != cap:
            info.magic = cap
    return info


@dataclass
class Dump:
    """1K 덤프 한 장. data 는 바이트 배열."""

    data: bytearray = field(default_factory=lambda: bytearray(SIZE_1K))

    @classmethod
    def load(cls, path: str | Path) -> "Dump":
        raw = Path(path).read_bytes()
        if len(raw) not in (SIZE_1K, 4096):   # 1K 또는 4K
            raise ValueError(
                "덤프 크기가 이상합니다: %d바이트 (1024 또는 4096이어야 합니다)" % len(raw)
            )
        return cls(bytearray(raw))

    def save(self, path: str | Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(bytes(self.data))
        return p

    def block(self, n: int) -> bytes:
        return bytes(self.data[n * BLOCK : (n + 1) * BLOCK])

    @property
    def uid(self) -> str:
        # 4바이트 UID 기준(블록 0 앞 4바이트).
        return self.data[0:4].hex().upper()

    def keys(self) -> list[tuple[str, str]]:
        """섹터별 (KeyA, KeyB) 16쌍을 트레일러에서 뽑는다."""
        out = []
        for s in range(SECTORS):
            tb = trailer_block(s)
            if (tb + 1) * BLOCK > len(self.data):
                break
            t = self.data[tb * BLOCK : (tb + 1) * BLOCK]
            out.append((t[0:6].hex().upper(), t[10:16].hex().upper()))
        return out

    def key_bytes(self) -> bytes:
        """pm3 가 쓰는 keyfile 형식: KeyA 16개 뒤에 KeyB 16개(각 6바이트)."""
        a = b"".join(bytes.fromhex(a) for a, _ in self.keys())
        b = b"".join(bytes.fromhex(b) for _, b in self.keys())
        return a + b

    def write_key_file(self, path: str | Path) -> Path:
        """트레일러의 키를 pm3 keyfile(hf-mf-<UID>-key.bin) 형식으로 저장."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(self.key_bytes())
        return p

    def pretty(self) -> str:
        lines = ["UID %s · %d바이트" % (self.uid, len(self.data)), ""]
        for s, (ka, kb) in enumerate(self.keys()):
            lines.append("  섹터 %2d  KeyA %s  KeyB %s" % (s, ka, kb))
        return "\n".join(lines)

    def empty_data_blocks(self) -> tuple[int, int]:
        """(전부 0인 데이터 블록 수, 전체 데이터 블록 수). 트레일러·블록0 은 뺀다."""
        zero = total = 0
        for b in range(min(BLOCKS, len(self.data) // BLOCK)):
            if is_trailer(b) or b == 0:
                continue
            total += 1
            if self.block(b) == b"\x00" * BLOCK:
                zero += 1
        return zero, total

    def block0_fields(self) -> dict[str, Any]:
        """블록 0(제조사 블록)을 분해한다.

        FM11RF08S 블록 0 = UID(4) · BCC(1) · SAK(1) · ATQA(2) · 제조사 바이트(8).
        제조사 바이트 8개 안에는 **서명(signature)처럼 보이는 6바이트**가 들어 있다
        (Fudan 이 UID 등에 대해 만들어 넣는 값 — 정확한 생성식은 비공개). 서명은
        UID 와 묶여 있어, 복제할 때 블록 0 을 그대로 옮겨야 서명이 어긋나지 않는다.
        """
        b0 = self.block(0)
        uid4 = b0[0:4]
        bcc = b0[4]
        bcc_calc = uid4[0] ^ uid4[1] ^ uid4[2] ^ uid4[3]
        return {
            "uid": uid4.hex().upper(),
            "bcc": "%02X" % bcc,
            "bcc_ok": bcc == bcc_calc,
            "sak": "%02X" % b0[5],
            # 블록0 에는 ATQA 가 리틀엔디안(04 00)으로 들어간다. pm3 표기(00 04)에 맞춰 뒤집는다.
            "atqa": bytes(reversed(b0[6:8])).hex().upper(),
            "manuf": b0[8:16].hex().upper(),       # 제조사 바이트 8개
            "signature": b0[10:16].hex().upper(),  # 그 중 서명으로 보이는 6바이트
        }

    def analyze(self) -> dict[str, Any]:
        """덤프를 뜯어보고 복제 가능 여부까지 판정해 돌려준다."""
        size = len(self.data)
        kind = {SIZE_1K: "MIFARE Classic 1K", 4096: "MIFARE Classic 4K"}.get(size, "비표준(%d B)" % size)
        sectors = []
        custom = 0
        all_default = True
        placeholders = []        # 데이터는 있는데 KeyA 가 FF 인 섹터 = 진짜 키가 가려진 '껍데기'
        for s, (ka, kb) in enumerate(self.keys()):
            tb = trailer_block(s)
            access = self.data[tb * BLOCK + 6 : tb * BLOCK + 10].hex().upper()
            da, db = is_default_key(ka), is_default_key(kb)
            if not da or not db:
                all_default = False
            if not da:
                custom += 1
            # 섹터에 실제 데이터(0 도 FF 도 아닌 블록)가 있는지.
            # 블록0 은 제외한다 — 어떤 카드든 제조사 데이터가 들어 있어, 숨은 키의 근거가 못 된다.
            has_data = False
            for b in range(s * BLOCKS_PER_SECTOR, s * BLOCKS_PER_SECTOR + BLOCKS_PER_SECTOR - 1):
                if b == 0:
                    continue
                blk = self.block(b)
                if blk != b"\x00" * BLOCK and blk != b"\xff" * BLOCK:
                    has_data = True
            placeholder = ka.upper() == "FFFFFFFFFFFF" and has_data
            if placeholder:
                placeholders.append(s)
            sectors.append({"sector": s, "keyA": ka, "keyB": kb, "access": access,
                            "keyA_default": da, "keyB_default": db, "placeholder": placeholder})
        zero, total = self.empty_data_blocks()
        valid = size in (SIZE_1K, 4096)

        # 값이 들어 있는(0 도 FF 도 아닌) 데이터 블록 — 블록0 과 트레일러는 뺀다
        data_blocks = []
        for b in range(min(BLOCKS, size // BLOCK)):
            if is_trailer(b) or b == 0:
                continue
            blk = self.block(b)
            if blk != b"\x00" * BLOCK and blk != b"\xff" * BLOCK:
                data_blocks.append({"block": b, "sector": sector_of(b), "hex": blk.hex().upper()})

        # 복제 판정
        warning = ""
        if placeholders:
            warning = ("섹터 %s 는 데이터는 있는데 KeyA 가 FF 입니다 — 백도어로 데이터만 읽고 "
                       "진짜 키가 안 들어간 '껍데기' 덤프일 수 있습니다. 이 상태로 복제하면 원본 키가 "
                       "복제되지 않습니다. 먼저 백도어 복구(fm11rf08s_recovery)로 진짜 키가 담긴 덤프/키 "
                       "파일을 받으세요." % placeholders)
        if not valid:
            magic = normal = "크기가 비표준이라 그대로 쓰기 어렵습니다."
        else:
            magic = ("가능 — gen1a 매직카드면 `hf mf cload` 로 블록0(UID %s·서명)까지 통째로 복제됩니다."
                     % self.uid)
            if all_default:
                normal = "가능 — 키가 전부 기본값이라 빈 카드에 쉽게 씁니다(일반 카드는 UID 변경 불가)."
            else:
                normal = ("조건부 — `hf mf restore` 로 쓰며, 덤프 트레일러에 진짜 키가 있어야 원본처럼 "
                          "동작합니다(사용자 키 섹터 %d개). 일반 카드는 UID(블록0) 변경 불가." % custom)

        return {
            "ok": valid,
            "size": size,
            "kind": kind,
            "uid": self.uid,
            "block0": self.block(0).hex().upper() if size >= BLOCK else "",
            "block0_fields": self.block0_fields() if size >= BLOCK else {},
            "sectors": sectors,
            "all_default_keys": all_default,
            "custom_sectors": custom,
            "placeholder_sectors": placeholders,
            "has_placeholder_keys": bool(placeholders),
            "empty_data_blocks": zero,
            "total_data_blocks": total,
            "data_blocks": data_blocks,
            # 블록0 을 뺀 데이터 블록이 '전부' 0일 때만 빈 카드로 본다
            # (섹터 하나에만 값이 있어도 빈 카드가 아니다 — 0.1.0 에서 놓쳤던 부분).
            "looks_blank": all_default and total > 0 and zero == total,
            "clone": {"magic": magic, "normal": normal, "warning": warning},
        }

    def report(self) -> str:
        a = self.analyze()
        f = a.get("block0_fields") or {}
        L = ["[덤프 분석]",
             "  종류    : %s (%d바이트)" % (a["kind"], a["size"]),
             "  블록0   : %s" % a["block0"]]
        if f:
            L += [
                "    UID   : %s   BCC %s(%s)   SAK %s   ATQA %s" % (
                    f["uid"], f["bcc"], "정상" if f["bcc_ok"] else "불일치", f["sak"], f["atqa"]),
                "    서명  : %s   (제조사 바이트 %s)" % (f["signature"], f["manuf"]),
            ]
        L += ["  키 상태 : %s" % ("전부 기본키" if a["all_default_keys"]
                                  else "사용자 키 섹터 %d개 포함" % a["custom_sectors"]),
             "  데이터  : 빈(0) 블록 %d/%d%s" % (a["empty_data_blocks"], a["total_data_blocks"],
                                               " — 완전히 빈 카드" if a["looks_blank"] else ""),
             ]
        if a["data_blocks"]:
            L.append("  값 있는 블록:")
            for db in a["data_blocks"]:
                L.append("    S%02d blk%02d  %s" % (db["sector"], db["block"], db["hex"]))
        L += ["",
             "[복제 가능 여부]",
             "  매직카드: %s" % a["clone"]["magic"],
             "  일반카드: %s" % a["clone"]["normal"]]
        if a["clone"].get("warning"):
            L += ["", "  ⚠ %s" % a["clone"]["warning"]]
        return "\n".join(L)
