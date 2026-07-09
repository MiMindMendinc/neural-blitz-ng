"""CLI tests."""

import subprocess
import sys

import pytest

from neural_blitz.cli import build_parser, main


@pytest.mark.unit
def test_cli_help():
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(["--help"])
    assert exc.value.code == 0


@pytest.mark.unit
def test_cli_version_subcommand(capsys):
    assert main(["version"]) == 0
    assert "neural-blitz" in capsys.readouterr().out


@pytest.mark.unit
def test_cli_version_json(capsys):
    assert main(["version", "--json"]) == 0
    assert '"version"' in capsys.readouterr().out


@pytest.mark.unit
def test_cli_validate_config_invalid():
    assert main(["validate-config", "/no/such/file.yaml"]) == 3


@pytest.mark.unit
def test_installed_entrypoint_help():
    result = subprocess.run(
        [sys.executable, "-m", "neural_blitz", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "test" in result.stdout
