from __future__ import annotations

from hotd_decompress.cli import main


def test_usage_exits_zero(capsys) -> None:
    assert main(["--usage"]) == 0
    out = capsys.readouterr().out
    assert "-d, --decompress" in out
    assert "PACK" in out


def test_help_and_h(capsys) -> None:
    assert main(["--help"]) == 0
    assert main(["-h"]) == 0
    out = capsys.readouterr().out
    assert out.count("Usage:") >= 2


def test_missing_export_path_is_usage_error(capsys) -> None:
    assert main(["-d"]) == 1
    err = capsys.readouterr().err
    assert "Usage:" in err
