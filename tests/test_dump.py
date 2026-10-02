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


def _dump_with_sector15_key(keyA: str) -> D.Dump:
    """섹터 15 블록60 에 데이터, 트레일러 KeyA/KeyB 를 지정해 만든다."""
    d = D.Dump()
    d.data[0:4] = bytes.fromhex("3359C8E4")
    d.data[60 * 16 : 60 * 16 + 16] = bytes.fromhex("600907924052340020201620202020CC")
    tb = D.trailer_block(15) * 16
    d.data[tb : tb + 6] = bytes.fromhex(keyA)
    d.data[tb + 6 : tb + 10] = bytes.fromhex("FF078069")
    d.data[tb + 10 : tb + 16] = bytes.fromhex(keyA)
    return d


def test_analyze_detects_placeholder_key():
    # 데이터는 있는데 KeyA 가 FF → 껍데기(백도어로 데이터만 읽은 덤프)
    a = _dump_with_sector15_key("FFFFFFFFFFFF").analyze()
    assert a["placeholder_sectors"] == [15]
    assert a["has_placeholder_keys"] is True
    assert a["clone"]["warning"]


def test_analyze_real_key_not_placeholder():
    a = _dump_with_sector15_key("23C7F6BAE3EB").analyze()
    assert a["placeholder_sectors"] == []
    assert a["custom_sectors"] == 1
    assert a["sectors"][15]["keyA"] == "23C7F6BAE3EB"


def test_block0_fields_parse():
    d = _dump_with_sector15_key("FFFFFFFFFFFF")
    d.data[0:16] = bytes.fromhex("3359C8E446080400030E7CF9B4B0AB90")
    f = d.block0_fields()
    assert f["uid"] == "3359C8E4"
    assert f["bcc"] == "46" and f["bcc_ok"] is True
    assert f["sak"] == "08"
    assert f["atqa"] == "0004"           # 블록0 의 04 00 을 뒤집어 표기
    assert f["signature"] == "7CF9B4B0AB90"


def test_key_file_roundtrip(tmp_path):
    d = _dump_with_sector15_key("23C7F6BAE3EB")
    kf = d.write_key_file(tmp_path / "hf-mf-3359C8E4-key.bin")
    assert kf.is_file()
    assert kf.stat().st_size == 16 * 6 * 2
    # 섹터15 KeyA 가 키파일 KeyA 영역(섹터15 = 오프셋 15*6)에 들어있다
    data = kf.read_bytes()
    assert data[15 * 6 : 15 * 6 + 6].hex().upper() == "23C7F6BAE3EB"
