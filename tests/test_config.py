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


def test_invalid_toml_is_not_silently_ignored(tmp_path):
    from amsrfid.config import ConfigError
    (tmp_path / "amsrfid.toml").write_text('pm3_path = "C:\\ProxSpace\\pm3.exe"')
    with pytest.raises(ConfigError, match="작은따옴표"):
        Config.load(tmp_path)


@pytest.mark.parametrize("value", ["-1", "0", "nan", '"oops"'])
def test_invalid_poll_rejected(tmp_path, value):
    from amsrfid.config import ConfigError
    (tmp_path / "amsrfid.toml").write_text("poll = " + value)
    with pytest.raises(ConfigError, match="poll"):
        Config.load(tmp_path)
