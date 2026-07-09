"""CLI conventions: --version/--help work; deferred commands refuse loudly."""

import pytest

from sovereign_monitor import __version__
from sovereign_monitor.__main__ import main


def test_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0
    assert f"sovereign-monitor {__version__}" in capsys.readouterr().out


def test_help_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--help"])
    assert excinfo.value.code == 0
    assert "ingest" in capsys.readouterr().out


def test_deferred_commands_refuse_to_run(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["build-index"]) == 2
    error_output = capsys.readouterr().err
    assert error_output.startswith("sovereign-monitor:")
    assert "not implemented" in error_output
