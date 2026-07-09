#!/usr/bin/env python3
"""Compatibility wrapper — delegates to the neural_blitz package."""

from neural_blitz.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
