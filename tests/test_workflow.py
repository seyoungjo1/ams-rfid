from __future__ import annotations

from pathlib import Path

from amsrfid import workflow
from amsrfid.config import Config
from tests.fakes import FakePm3


def _cfg(tmp_path: Path) -> Config:
    return Config(outdir=str(tmp_path / "out"), timeout=5, poll=0.01, wait=1, root=tmp_path)


def test_identify_detects_fm11rf08s(tmp_path):
    pm3 = FakePm3(workdir=tmp_path)
    info = workflow.identify(pm3, echo=lambda *_: None)
    assert info.uid == "DEADBEEF"
    assert info.is_fm11rf08s is True
    assert info.backdoor is True


def test_recover_and_dump_saves_bin(tmp_path):
    cfg = _cfg(tmp_path)
    pm3 = FakePm3(workdir=cfg.out_path)
    info = workflow.identify(pm3, echo=lambda *_: None)
    res = workflow.recover_and_dump(pm3, info, cfg, echo=lambda *_: None)
    assert res.recovered is True
    assert res.bin_path is not None and res.bin_path.is_file()
    assert res.bin_path.stat().st_size == 1024
    # 원터치가 만든 최종 파일 이름에 UID 가 들어간다
    assert "DEADBEEF" in res.bin_path.name


def test_recover_and_dump_failure_gives_note(tmp_path):
    cfg = _cfg(tmp_path)
    pm3 = FakePm3(workdir=cfg.out_path, autopwn_ok=False)
    info = workflow.identify(pm3, echo=lambda *_: None)
    res = workflow.recover_and_dump(pm3, info, cfg, echo=lambda *_: None)
    assert res.recovered is False
    assert "fm11rf08s_recovery" in res.note


def test_clone_guard_blocks_placeholder_dump(tmp_path):
    import pytest
    from amsrfid import dump as D
    cfg = _cfg(tmp_path)
    cfg.out_path.mkdir(parents=True)
    # 데이터는 있는데 KeyA 가 FF 인 껍데기 덤프
    d = D.Dump()
    d.data[0:4] = bytes.fromhex("3359C8E4")
    d.data[60 * 16 : 60 * 16 + 16] = bytes.fromhex("600907924052340020201620202020CC")
    tb = D.trailer_block(15) * 16
    d.data[tb : tb + 6] = b"\xff" * 6
    d.data[tb + 10 : tb + 16] = b"\xff" * 6
    p = d.save(cfg.out_path / "placeholder.bin")
    pm3 = FakePm3(workdir=cfg.out_path, magic="Gen 1a")
    with pytest.raises(workflow.WorkflowError):
        workflow.clone_to_card(pm3, p, cfg, echo=lambda *a: None)


def test_clone_to_card_writes(tmp_path):
    cfg = _cfg(tmp_path)
    pm3 = FakePm3(workdir=cfg.out_path, magic="Gen 1a")
    # 먼저 떠 둔 .bin 하나 만든다
    info = workflow.identify(pm3, echo=lambda *_: None)
    res = workflow.recover_and_dump(pm3, info, cfg, echo=lambda *_: None)
    # 복제(쓰기) — cload 명령이 불려야 한다
    workflow.clone_to_card(pm3, res.bin_path, cfg, echo=lambda *_: None)
    assert any("cload" in c for c in pm3.commands)
