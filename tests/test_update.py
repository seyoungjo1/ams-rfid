from __future__ import annotations

from amsrfid import update


def test_exclusions():
    assert update.is_excluded("token.txt")
    assert update.is_excluded("amsrfid.toml")
    assert update.is_excluded("out/ams-DEAD.bin")
    assert update.is_excluded("backup/20240101/x")
    assert update.is_excluded("tests/test_dump.py")
    assert not update.is_excluded("amsrfid/cli.py")
    assert not update.is_excluded("run.bat")
    assert not update.is_excluded("VERSION")


def test_list_paths_skips_excluded_and_dirs():
    tree = {
        "truncated": False,
        "tree": [
            {"type": "blob", "path": "amsrfid/cli.py"},
            {"type": "blob", "path": "token.txt"},
            {"type": "blob", "path": "out/x.bin"},
            {"type": "tree", "path": "amsrfid"},
            {"type": "blob", "path": "VERSION"},
        ],
    }
    paths = set(update.list_paths(tree))
    assert paths == {"amsrfid/cli.py", "VERSION"}


def test_apply_backs_up_and_writes(tmp_path):
    (tmp_path / "VERSION").write_text("0.1.0")
    (tmp_path / "amsrfid").mkdir()
    (tmp_path / "amsrfid" / "cli.py").write_text("old\n")
    blobs = {
        "amsrfid/cli.py": b"new\n",
        "amsrfid/__init__.py": b"__version__='x'\n",
        "VERSION": b"0.2.0",
    }
    res = update.apply(blobs, "0.2.0", root=tmp_path)
    # import_check 는 꾸러미가 온전치 않으면 건너뛴다(여기선 부품 몇 개뿐) → 실패 없음
    assert not res["failed"]
    assert (tmp_path / "amsrfid" / "cli.py").read_text() == "new\n"
    assert (tmp_path / "VERSION").read_text() == "0.2.0"
    # 바뀐 파일은 backup/<시각>/ 에 옛 내용이 남는다
    backups = list((tmp_path / "backup").glob("*/amsrfid/cli.py"))
    assert backups and backups[0].read_text() == "old\n"


def test_apply_running_bat_deferred(tmp_path, monkeypatch):
    monkeypatch.setenv("AMSRFID_RUNNING_BAT", r"C:\ams\run.bat")
    (tmp_path / "run.bat").write_text("old bat\n")
    (tmp_path / "VERSION").write_text("0.1.0")
    blobs = {"run.bat": b"new bat\n", "VERSION": b"0.2.0"}
    res = update.apply(blobs, "0.2.0", root=tmp_path)
    # 지금 돌고 있는 run.bat 은 못 덮어쓰므로 run_v020.bat 로 떨어진다
    assert res["deferred"] == ["run_v020.bat"]
    assert (tmp_path / "run_v020.bat").read_text() == "new bat\n"
    assert (tmp_path / "run.bat").read_text() == "old bat\n"


def test_failed_update_keeps_old_version(tmp_path, monkeypatch):
    (tmp_path / "VERSION").write_text("0.2.6")
    monkeypatch.setattr(update, "import_check", lambda *a: ["import failed"])
    res = update.apply({"VERSION": b"0.2.7", "app.txt": b"updated"}, "0.2.7", tmp_path)
    assert res["failed"]
    assert (tmp_path / "VERSION").read_text() == "0.2.6"
