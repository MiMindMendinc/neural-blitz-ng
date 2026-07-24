"""Tests that the published configuration schema matches runtime settings."""

from __future__ import annotations

import json
from dataclasses import fields
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from neural_blitz.config import MonitorConfig, ServerConfig, TestConfig, validate_config_file, write_sample_config

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "neural_blitz.schema.json"


def _schema() -> dict[str, object]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


@pytest.mark.unit
def test_schema_matches_all_runtime_config_fields():
    schema = _schema()
    definitions = schema["$defs"]  # type: ignore[index]
    assert set(definitions["test_properties"]["properties"]) == {field.name for field in fields(TestConfig)}  # type: ignore[index]
    assert set(definitions["server"]["properties"]) == {field.name for field in fields(ServerConfig)}  # type: ignore[index]
    assert set(definitions["monitor"]["properties"]) == {field.name for field in fields(MonitorConfig)}  # type: ignore[index]


@pytest.mark.unit
@pytest.mark.parametrize(
    "config_path",
    [
        ROOT / "neural_blitz.yaml",
        ROOT / "examples" / "neural_blitz.yaml",
        ROOT / "examples" / "docker-neural_blitz.yaml",
    ],
)
def test_examples_validate_against_strict_schema(config_path: Path):
    assert validate_config_file(str(config_path)) == []


@pytest.mark.unit
def test_generated_config_validates_against_strict_schema(tmp_path: Path):
    config_path = tmp_path / "generated.yaml"
    write_sample_config(str(config_path))
    assert validate_config_file(str(config_path)) == []


@pytest.mark.unit
@pytest.mark.parametrize(
    "content",
    [
        "unknown: true\n",
        "defaults:\n  unknown: true\n",
        "server:\n  unknown: true\n",
        "monitor:\n  unknown: true\n",
        "targets:\n  - host: 127.0.0.1\n    unknown: true\n",
    ],
)
def test_strict_schema_rejects_unknown_keys(tmp_path: Path, content: str):
    config_path = tmp_path / "unknown.yaml"
    config_path.write_text(content, encoding="utf-8")
    errors = validate_config_file(str(config_path))
    assert any(
        error.startswith("schema ")
        and ("unevaluated properties" in error.lower() or "additional properties" in error.lower())
        for error in errors
    )


@pytest.mark.unit
def test_schema_itself_is_valid():
    Draft202012Validator.check_schema(_schema())
