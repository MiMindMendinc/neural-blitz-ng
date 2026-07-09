"""Additional config validation tests."""

from pathlib import Path

import pytest

from neural_blitz.config import read_yaml, validate_config_file
from neural_blitz.errors import ConfigError


@pytest.mark.unit
def test_read_yaml_rejects_non_mapping(tmp_path: Path):
    path = tmp_path / "list.yaml"
    path.write_text("- not a mapping\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="mapping"):
        read_yaml(path)


@pytest.mark.unit
def test_validate_config_bad_monitor_section(tmp_path: Path):
    path = tmp_path / "bad.yaml"
    path.write_text("monitor: not-a-dict\ntargets:\n  - label: x\n    host: 127.0.0.1\n    port: 1\n", encoding="utf-8")
    errors = validate_config_file(str(path))
    assert any("monitor" in e for e in errors)
