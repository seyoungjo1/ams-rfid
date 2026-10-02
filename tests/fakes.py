"""테스트용 가짜 pm3 — 실제 하드웨어 없이 흐름을 검증한다."""
from __future__ import annotations

from pathlib import Path

from amsrfid import dump as D
from amsrfid.pm3 import Pm3Result


class FakePm3:
    """Pm3 를 흉내 낸다. 명령 글자에 따라 미리 정한 출력을 돌려준다."""

    def __init__(self, uid="DEADBEEF", fm11rf08s=True, magic="", workdir: Path | None = None,
                 autopwn_ok=True):
        self.uid = uid
        self.fm11rf08s = fm11rf08s
        self.magic = magic
        self.workdir = workdir
        self.autopwn_ok = autopwn_ok
        self.client = "fake-pm3"
        self.port = None
        self.commands: list[str] = []

    def device_present(self) -> bool:
        return True

    def card_present(self) -> bool:
        return True

    def _dump_bytes(self) -> bytes:
        d = D.Dump()
        d.data[0:4] = bytes.fromhex(self.uid)
        tb = D.trailer_block(0) * D.BLOCK
        d.data[tb : tb + 6] = bytes.fromhex("A0A1A2A3A4A5")
        d.data[tb + 10 : tb + 16] = bytes.fromhex("B0B1B2B3B4B5")
        return bytes(d.data)

    def run(self, commands, timeout=180) -> Pm3Result:
        if isinstance(commands, str):
            commands = [commands]
        self.commands.extend(commands)
        joined = " ; ".join(commands)

        if "hf 14a info" in joined:
            return Pm3Result(0, "UID: %s\nATQA: 00 04\nSAK: 08\n" % " ".join(
                self.uid[i:i+2] for i in range(0, len(self.uid), 2)), "")
        if "hf mf info" in joined:
            txt = ""
            if self.fm11rf08s:
                txt += "Fudan FM11RF08S\nBackdoor coms supported: present (key A396EFA4E24F)\n"
            txt += "Magic capabilities... %s\n" % (self.magic or "n/a")
            return Pm3Result(0, txt, "")
        if "fm11rf08s_recovery" in joined or "hf mf autopwn" in joined:
            # FM11RF08S 는 recovery 스크립트, 일반 카드는 autopwn — 둘 다 성공 시 덤프를 떨군다.
            if self.autopwn_ok and self.workdir is not None:
                Path(self.workdir).mkdir(parents=True, exist_ok=True)
                (Path(self.workdir) / ("hf-mf-%s-dump.bin" % self.uid)).write_bytes(self._dump_bytes())
                (Path(self.workdir) / ("hf-mf-%s-key.bin" % self.uid)).write_bytes(b"\x00" * 192)
                return Pm3Result(0, "[+] found all keys\n[+] Saved to hf-mf-%s-dump.bin\n" % self.uid, "")
            return Pm3Result(0, "[-] recovery failed on some sectors\n", "")
        if "cload" in joined or "restore" in joined:
            return Pm3Result(0, "[+] wrote all blocks\n", "")
        return Pm3Result(0, "hw version: Proxmark3 RDV4\nos: ...\n", "")
