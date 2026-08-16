"""Operator config profiles and init-config packaging."""

import json
from pathlib import Path

import pytest

from neural_blitz.cli import main
from neural_blitz.config import (
    CONFIG_PROFILES,
    PROFILE_SLA_FILES,
    PROFILES_DIR,
    list_config_profiles,
    validate_config_file,
    write_sample_config,
)
from neural_blitz.errors import ConfigError
from neural_blitz.prometheus import METRIC_DESCRIPTORS
from neural_blitz.sla import load_sla, validate_sla_config


@pytest.mark.unit
def test_list_config_profiles_matches_packaged_files():
    profiles = list_config_profiles()
    assert set(profiles) == set(CONFIG_PROFILES)
    for name in profiles:
        assert (PROFILES_DIR / f"{name}.yaml").is_file()
        assert (PROFILES_DIR / PROFILE_SLA_FILES[name]).is_file()


@pytest.mark.unit
@pytest.mark.parametrize("profile", sorted(CONFIG_PROFILES))
def test_write_sample_config_profile_validates(tmp_path: Path, profile: str):
    destination = tmp_path / "neural_blitz.yaml"
    written = write_sample_config(str(destination), profile=profile)
    assert destination.exists()
    sla_path = tmp_path / PROFILE_SLA_FILES[profile]
    assert sla_path.exists()
    assert written == [str(destination), str(sla_path)]
    assert validate_config_file(str(destination)) == []
    assert validate_sla_config(load_sla(str(sla_path))) == []


@pytest.mark.unit
def test_write_sample_config_rejects_unknown_profile(tmp_path: Path):
    with pytest.raises(ConfigError, match="Unknown config profile"):
        write_sample_config(str(tmp_path / "x.yaml"), profile="carrier-grade")


@pytest.mark.unit
def test_write_sample_config_rejects_missing_profile_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(Path, "is_file", lambda self: False)
    with pytest.raises(ConfigError, match="Packaged profile is missing"):
        write_sample_config(str(tmp_path / "x.yaml"), profile="local")


@pytest.mark.unit
def test_write_sample_config_rejects_missing_sla_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    original = Path.is_file

    def fake_is_file(self: Path) -> bool:
        if self.name.startswith("sla-"):
            return False
        return original(self)

    monkeypatch.setattr(Path, "is_file", fake_is_file)
    with pytest.raises(ConfigError, match="Packaged SLA"):
        write_sample_config(str(tmp_path / "x.yaml"), profile="local")


@pytest.mark.unit
def test_cli_list_profiles(capsys: pytest.CaptureFixture[str]):
    assert main(["init-config", "--list-profiles"]) == 0
    output = capsys.readouterr().out
    assert "starlink" in output
    assert "mesh" in output
    assert "nonprofit" in output


@pytest.mark.unit
def test_cli_list_profiles_json(capsys: pytest.CaptureFixture[str]):
    assert main(["init-config", "--list-profiles", "--json"]) == 0
    output = capsys.readouterr().out
    assert '"name": "starlink"' in output
    assert '"profiles"' in output


@pytest.mark.unit
def test_cli_init_config_starlink_profile(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    destination = tmp_path / "site.yaml"
    assert main(["--no-rich", "init-config", "--profile", "starlink", "--output", str(destination)]) == 0
    text = destination.read_text(encoding="utf-8")
    assert "starlink-uplink" in text
    assert (tmp_path / "sla-starlink.yaml").exists()
    assert "Next:" in capsys.readouterr().out


@pytest.mark.unit
def test_grafana_dashboard_covers_all_prometheus_metrics():
    dashboard = json.loads(Path("examples/grafana-dashboard.json").read_text(encoding="utf-8"))
    assert dashboard["uid"] == "neural-blitz-ng"
    blob = json.dumps(dashboard)
    for descriptor in METRIC_DESCRIPTORS:
        assert descriptor.name in blob
    exprs = [target.get("expr", "") for panel in dashboard["panels"] for target in panel.get("targets", [])]
    assert exprs
    assert all("rate(" not in expr and "increase(" not in expr for expr in exprs)
