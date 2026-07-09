"""Additional configuration tests."""

from pathlib import Path

import pytest

from neural_blitz.config import (
    coerce_bool,
    get_config_section,
    write_sample_config,
)
from neural_blitz.errors import ConfigError


@pytest.mark.unit
def test_coerce_bool_invalid():
    with pytest.raises(ConfigError):
        coerce_bool("maybe")


@pytest.mark.unit
def test_get_config_section_merges_defaults():
    data = {"defaults": {"count": 500}, "test": {"host": "127.0.0.1", "port": 9999}}
    merged = get_config_section(data, "test")
    assert merged["count"] == 500
    assert merged["host"] == "127.0.0.1"


@pytest.mark.unit
def test_write_sample_config(tmp_path: Path):
    path = tmp_path / "sample.yaml"
    write_sample_config(str(path))
    text = path.read_text(encoding="utf-8")
    assert "targets:" in text
    assert "monitor:" in text
