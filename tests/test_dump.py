from __future__ import annotations

from amsrfid import dump as D


def _make_1k() -> D.Dump:
    d = D.Dump()
    # 블록 0 앞 4바이트 = UID
    d.data[0:4] = bytes.fromhex("DEADBEEF")
    # 섹터 0 트레일러: KeyA=A0.., KeyB=B0..
    tb = D.trailer_block(0) * D.BLOCK
    d.data[tb : tb + 6] = bytes.fromhex("A0A1A2A3A4A5")
    d.data[tb + 10 : tb + 16] = bytes.fromhex("B0B1B2B3B4B5")
    return d


def test_sizes_and_layout():
    assert D.SIZE_1K == 1024
    assert D.BLOCKS == 64
    assert D.trailer_block(0) == 3
    assert D.trailer_block(1) == 7
    assert D.is_trailer(3) and not D.is_trailer(2)
    assert D.sector_of(7) == 1


def test_roundtrip_and_keys(tmp_path):
    d = _make_1k()
    p = d.save(tmp_path / "x.bin")
    assert p.is_file() and p.stat().st_size == 1024
    back = D.Dump.load(p)
    assert back.uid == "DEADBEEF"
    ka, kb = back.keys()[0]
    assert ka == "A0A1A2A3A4A5"
    assert kb == "B0B1B2B3B4B5"
    assert len(back.keys()) == 16
    # keyfile 형식: KeyA 16개(96바이트) + KeyB 16개(96바이트)
    assert len(back.key_bytes()) == 16 * 6 * 2


def test_load_rejects_bad_size(tmp_path):
    p = tmp_path / "bad.bin"
    p.write_bytes(b"\x00" * 100)
    try:
        D.Dump.load(p)
    except ValueError:
        return
    raise AssertionError("크기가 이상하면 ValueError 가 나야 합니다")


def test_parse_14a_info():
    text = """
    [+]  UID: DE AD BE EF
    [+] ATQA: 00 04
    [+]  SAK: 08 [2]
    """
    info = D.parse_14a_info(text)
    assert info.uid == "DEADBEEF"
    assert info.atqa == "0004"
    assert info.sak == "08"


def test_parse_mf_info_fm11rf08s_backdoor():
    text = """
    [=] --- Fudan FM11RF08S
    [+] Backdoor coms supported: present (key A396EFA4E24F)
    [+] Magic capabilities... n/a
    """
    info = D.parse_mf_info(text)
    assert info.is_fm11rf08s is True
    assert info.backdoor is True
    assert info.magic == ""


def test_parse_mf_info_magic():
    text = "[+] Magic capabilities... Gen 1a"
    info = D.parse_mf_info(text)
    assert "gen 1a" in info.magic.lower()
