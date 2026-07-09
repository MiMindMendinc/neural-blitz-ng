"""Application-wide constants."""

from __future__ import annotations

import struct

__version__ = "9.0.0"
APP_NAME = "neural-blitz"
DEFAULT_CONFIG_BASENAME = "neural_blitz.yaml"
SUPPORTED_METRICS_SUFFIXES = {".json", ".csv"}

# Packet protocol
PACKET_VERSION = 1
HEADER_STRUCT = struct.Struct("!BQQq")  # version, seq_id, send_ns, scheduled_ns
HEADER_SIZE = HEADER_STRUCT.size

# Exit codes
EXIT_SUCCESS = 0
EXIT_RUNTIME_ERROR = 1
EXIT_SLA_FAILURE = 2
EXIT_CONFIG_ERROR = 3
EXIT_COMPARISON_FAILURE = 4
EXIT_SAFETY_VIOLATION = 5
EXIT_DEPENDENCY_MISSING = 6
EXIT_INTERRUPTED = 130

# Default safety ceilings (override via env with NEURAL_BLITZ_MAX_*)
DEFAULT_MAX_COUNT = 1_000_000
DEFAULT_MAX_CONCURRENCY = 10_000
DEFAULT_MAX_RATE = 100_000.0
DEFAULT_MAX_PACKET_SIZE = 65_507
DEFAULT_MIN_TIMEOUT = 0.01
DEFAULT_MAX_TIMEOUT = 60.0

# Localhost / private ranges considered safe without explicit authorization
SAFE_TARGET_HOSTS = frozenset(
    {
        "localhost",
        "127.0.0.1",
        "::1",
        "0.0.0.0",
    }
)
