"""end-to-end 테스트 — FakePm3 객체가 아니라 '진짜 서브프로세스'(가상 스텁)로 검증.

ams-rfid 가 실제로 `proxmark3 -p COM -c "..."` 를 돌리고, 그 출력을 파싱하고, 떨어진
덤프 파일을 찾아 저장/검증하는 전 과정을 실제 프로세스 실행으로 돌려 본다.

스텁은 shebang+실행권한으로 직접 실행하므로 Linux/macOS 에서만 돈다(Windows 는 유닛
테스트·소스검사·임포트로 커버). CI 는 ubuntu 에서 이 e2e 를, windows 에서 나머지를 돌린다.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from amsrfid import workflow, dump as D
from amsrfid.config import Config
from amsrfid.pm3 import Pm3

STUB = Path(__file__).parent / "stub" / "proxmark3_stub.py"
pytestmark = pytest.mark.skipif(os.name == "nt", reason="스텁은 shebang 실행 — Linux/macOS 전용")


def _make_executable(p: Path) -> None:
    p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _cfg(tmp_path: Path) -> Config:
    cfg = Config(outdir=str(tmp_path / "out"), timeout=30, poll=0.01, wait=2, root=tmp_path)
    cfg.out_path.mkdir(parents=True, exist_ok=True)
    return cfg


def test_e2e_identify_and_recover(tmp_path):
    _make_executable(STUB)
    cfg = _cfg(tmp_path)
    pm3 = Pm3(client=str(STUB), port="COM_TEST", workdir=cfg.out_path)

    info = workflow.identify(pm3, echo=lambda *a: None)
    assert info.uid == "DEADBEEF"
    assert info.is_fm11rf08s is True

    res = workflow.recover_and_dump(pm3, info, cfg, echo=lambda *a: None)
    assert res.recovered is True
    assert res.bin_path is not None and res.bin_path.is_file()
    assert res.bin_path.stat().st_size == 1024
    # 저장된 .bin 을 다시 읽어 UID 가 맞는지
    assert D.Dump.load(res.bin_path).uid == "DEADBEEF"


def test_e2e_clone_and_verify(tmp_path):
    _make_executable(STUB)
    cfg = _cfg(tmp_path)
    pm3 = Pm3(client=str(STUB), port="COM_TEST", workdir=cfg.out_path)

    # 먼저 떠 둔 .bin 하나 만든다
    info = workflow.identify(pm3, echo=lambda *a: None)
    res = workflow.recover_and_dump(pm3, info, cfg, echo=lambda *a: None)
    assert res.recovered

    # 복제(gen1a → cload) + 되읽어 검증까지 실제 서브프로세스로
    logs = []
    workflow.clone_to_card(pm3, res.bin_path, cfg, echo=lambda m: logs.append(str(m)))
    joined = "\n".join(logs)
    assert "복제 시도 완료" in joined
    # 되읽기 검증이 돌아 결과를 남겼는지(일치/불일치/불가 중 하나)
    assert any(k in joined for k in ("검증 OK", "불일치", "되읽기 실패"))


def test_e2e_device_and_card_present(tmp_path):
    _make_executable(STUB)
    cfg = _cfg(tmp_path)
    pm3 = Pm3(client=str(STUB), port="COM_TEST", workdir=cfg.out_path)
    assert pm3.device_present() is True
    assert pm3.card_present() is True
