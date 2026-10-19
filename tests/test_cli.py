from __future__ import annotations

from pathlib import Path

from hotd_decompress.cli import main


def test_usage_exits_zero(capsys) -> None:
    assert main(["--usage"]) == 0
    out = capsys.readouterr().out
    assert "-d, --decompress" in out
    assert "PACK" in out
    assert "-a, --all" in out
    assert "-p --all" in out


def test_help_and_h(capsys) -> None:
    assert main(["--help"]) == 0
    assert main(["-h"]) == 0
    out = capsys.readouterr().out
    assert out.count("Usage:") >= 2


def test_missing_export_path_is_usage_error(capsys) -> None:
    assert main(["-d"]) == 1
    err = capsys.readouterr().err
    assert "Usage:" in err


def test_all_missing_assets_is_error(tmp_path: Path, capsys) -> None:
    missing = tmp_path / "nope"
    assert main(["--all", str(missing)]) == 1
    err = capsys.readouterr().err
    assert "not found" in err


def test_png_all_empty_tree_is_error(tmp_path: Path, capsys) -> None:
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "sound").mkdir()
    assert main(["-p", "--all", str(assets)]) == 1
    err = capsys.readouterr().err
    assert "No matching assets" in err


def test_all_narrowed_to_evt(tmp_path: Path, capsys) -> None:
    assets = tmp_path / "assets"
    (assets / "evt/allstage").mkdir(parents=True)
    assert main(["--all", "-e", str(assets)]) == 1
    err = capsys.readouterr().err
    assert "evt" in err
    assert "No matching assets" in err
