"""Logging setup tests."""

import logging

import pytest

from neural_blitz.errors import ConfigError
from neural_blitz.logging_setup import configure_logging, emit_error


@pytest.mark.unit
def test_configure_logging_plain():
    configure_logging("INFO", use_rich=False)
    assert logging.getLogger().level == logging.INFO


@pytest.mark.unit
def test_configure_logging_invalid_level():
    with pytest.raises(ConfigError):
        configure_logging("NOTALEVEL", use_rich=False)


@pytest.mark.unit
def test_emit_error_plain(capsys):
    emit_error("something failed", use_rich=False)
    assert "something failed" in capsys.readouterr().err
