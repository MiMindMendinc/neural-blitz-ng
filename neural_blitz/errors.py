"""Application exception types."""

from __future__ import annotations


class NeuralBlitzError(Exception):
    """Base application error."""


class ConfigError(NeuralBlitzError):
    """Raised when configuration is invalid."""


class MetricsError(NeuralBlitzError):
    """Raised when metrics files cannot be read or written."""


class SLAFailure(NeuralBlitzError):
    """Raised when SLA checks fail."""


class ComparisonFailure(NeuralBlitzError):
    """Raised when metrics comparison fails regression thresholds."""


class SafetyViolation(NeuralBlitzError):
    """Raised when safety limits or authorized-use policy is violated."""


class DependencyMissing(NeuralBlitzError):
    """Raised when an optional dependency is required but not installed."""
