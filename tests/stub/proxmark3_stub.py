#!/usr/bin/env python3
"""가상 Proxmark3 클라이언트(스텁) — 실제 하드웨어 없이 end-to-end 테스트용.

진짜 proxmark3 클라이언트처럼 `-p <port>` 와 `-c "<command>"` 를 받아, 명령에 맞는 가짜
출력을 내고 필요하면 덤프 파일(hf-mf-<UID>-dump.bin)을 현재 폴더에 떨군다. ams-rfid 가
서브프로세스로 이걸 호출하면, FakePm3 객체가 아니라 '진짜 서브프로세스 경로'(명령 전달·
출력 파싱·덤프 파일 탐지)를 그대로 검증할 수 있다.
"""
import os
import sys

UID = "DEADBEEF"


def _parse(argv):
    cmds = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "-c" and i + 1 < len(argv):
            cmds = [argv[i + 1]]; i += 2  # Upstream keeps only the last -c argument.
        elif a == "-p" and i + 1 < len(argv):
            i += 2
        else:
            i += 1
    return cmds


def _write_dump():
    d = bytearray(1024)
    d[0:4] = bytes.fromhex(UID)
    d[4] = 0x46            # BCC
    d[5] = 0x08            # SAK
    d[6:8] = bytes([0x04, 0x00])
    t0 = 3 * 16            # 섹터0 트레일러
    d[t0:t0 + 6] = bytes.fromhex("A0A1A2A3A4A5")
    d[t0 + 6:t0 + 10] = bytes.fromhex("FF078069")
    d[t0 + 10:t0 + 16] = bytes.fromhex("B0B1B2B3B4B5")
    with open("hf-mf-%s-dump.bin" % UID, "wb") as f:
        f.write(bytes(d))
    with open("hf-mf-%s-key.bin" % UID, "wb") as f:
        f.write(b"\x00" * 192)


def main():
    joined = " ; ".join(_parse(sys.argv[1:]))
    out = []
    if "hw version" in joined or "hw status" in joined:
        out.append("[=] Proxmark3 RDV4\n[=] os: v4.0\n[=] client: v4.0")
    if "hf 14a info" in joined:
        out.append("[+]  UID: DE AD BE EF\n[+] ATQA: 00 04\n[+]  SAK: 08")
    if "hf mf info" in joined:
        out.append("[=] --- Fudan FM11RF08S\n[+] Backdoor coms supported: present (key A396EFA4E24F)\n[+] Magic capabilities... Gen 1a")
    if "isen" in joined and "--help" in joined:
        out.append("--collect_fm11rf08s_with_data   collect nonces with data")
    if "fm11rf08s_recovery" in joined or "hf mf autopwn" in joined:
        _write_dump()
        out.append("[+] found all keys\n[+] Saved to hf-mf-%s-dump.bin\nHave a nice day!" % UID)
    if "hf mf dump" in joined:
        _write_dump()
        out.append("[+] Dumped card data to hf-mf-%s-dump.bin\nHave a nice day!" % UID)
    if "cload" in joined or "restore" in joined:
        out.append("[+] Wrote all blocks\nHave a nice day!")
    sys.stdout.write("\n".join(out) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
