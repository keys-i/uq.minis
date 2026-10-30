"""Shared test paths without importing fixtures or optional runtime packages

Feature suites own their local setup; reusable fixture protocols remain in
``tests.fixtures`` and stateful service doubles live in ``tests.fakes``
"""

from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
