"""Compare output tests."""

from pathlib import Path

import pytest

from neural_blitz.compare import write_comparison_output
from neural_blitz.metrics import LatencyStats


@pytest.mark.unit
def test_write_comparison_output(tmp_path: Path):
    path = tmp_path / "cmp.json"
    write_comparison_output(str(path), {"passed": True, "comparison": []})
    assert path.exists()
    assert '"passed"' in path.read_text(encoding="utf-8")
