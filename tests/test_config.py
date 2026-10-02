from __future__ import annotations

import sys

import pytest

from amsrfid.config import Config


def test_defaults(tmp_path):
    cfg = Config.load(root=tmp_path)
    assert cfg.outdir == "out"
    assert cfg.out_path == tmp_path / "out"
    assert cfg.timeout == 300
    assert cfg.wait == 120


@pytest.mark.skipif(sys.version_info < (3, 11), reason="tomllib 필요")
def test_reads_toml(tmp_path):
    (tmp_path / "amsrfid.toml").write_text(
        'pm3_path = "C:/pm3/pm3.bat"\noutdir = "dumps"\ntimeout = 99\n',
        encoding="utf-8",
    )
    cfg = Config.load(root=tmp_path)
    assert cfg.pm3_path == "C:/pm3/pm3.bat"
    assert cfg.outdir == "dumps"
    assert cfg.timeout == 99
    assert cfg.out_path == tmp_path / "dumps"
