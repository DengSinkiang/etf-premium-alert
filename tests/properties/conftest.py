"""Shared fixtures for property-based tests."""

import tempfile
from pathlib import Path

import pytest

from src.premium_store import PremiumStore


@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> str:
    """Provide a temporary directory for PremiumStore tests."""
    return str(tmp_path)


@pytest.fixture
def premium_store(tmp_data_dir: str) -> PremiumStore:
    """Provide a PremiumStore instance backed by a temporary directory."""
    return PremiumStore(data_dir=tmp_data_dir)
