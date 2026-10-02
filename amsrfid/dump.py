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

BLOCK = 16          # 바이트
BLOCKS_PER_SECTOR = 4
SECTORS = 16
BLOCKS = SECTORS * BLOCKS_PER_SECTOR        # 64
SIZE_1K = BLOCKS * BLOCK                      # 1024

# FM11RF08* 계열의 공개된 백도어 키(Fudan, 2024 Teuwen 연구). pm3 가 키 복구에 쓴다.
FM11RF08S_BACKDOOR = "A396EFA4E24F"


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

    def pretty(self) -> str:
        lines = ["UID %s · %d바이트" % (self.uid, len(self.data)), ""]
        for s, (ka, kb) in enumerate(self.keys()):
            lines.append("  섹터 %2d  KeyA %s  KeyB %s" % (s, ka, kb))
        return "\n".join(lines)
