"""Property-based tests for performance optimization features.

Tests cover:
- AKShare DataFrame caching (Properties 1-4)
- Parallel ETF processing in Monitor (Properties 5-6)
- PremiumStore I/O consolidation (Properties 7-9)

Library: Hypothesis
Configuration: @settings(max_examples=100)
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from src.akshare_source import AKShareSource
from src.exceptions import DataFetchError, StoreError
from src.models import (
    AppConfig,
    ETFConfig,
    ETFData,
    MonitorResult,
    PremiumRecord,
    PremiumRule,
    TelegramConfig,
)
from src.monitor import Monitor
from src.premium_store import PremiumStore


# ---------------------------------------------------------------------------
# Hypothesis strategies for generating test data
# ---------------------------------------------------------------------------

# ETF codes: 6-digit numeric strings
etf_codes = st.text(
    min_size=6, max_size=6, alphabet=st.characters(whitelist_categories=("Nd",))
)

# Premium rates: realistic float values (percentage)
premium_rates = st.floats(min_value=-20.0, max_value=50.0, allow_nan=False, allow_infinity=False)

# Timestamps within the last 60 days (covers both within and beyond 30-day window)
timestamps = st.datetimes(
    min_value=datetime(2024, 1, 1),
    max_value=datetime(2025, 12, 31),
)

# Premium rules for ETF config generation
premium_rules_strategy = st.builds(
    PremiumRule,
    max_premium=st.floats(min_value=-5.0, max_value=10.0, allow_nan=False, allow_infinity=False),
    min_ratio=st.floats(min_value=0.0, max_value=0.5, allow_nan=False, allow_infinity=False),
    max_ratio=st.floats(min_value=0.5, max_value=1.0, allow_nan=False, allow_infinity=False),
)

# ETF config for Monitor tests
etf_config_strategy = st.builds(
    ETFConfig,
    code=etf_codes,
    name=st.text(min_size=1, max_size=20),
    target_amount=st.floats(min_value=1000.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
    bought_amount=st.floats(min_value=0.0, max_value=50000.0, allow_nan=False, allow_infinity=False),
    premium_rules=st.lists(premium_rules_strategy, min_size=1, max_size=3),
)


# ---------------------------------------------------------------------------
# Property tests will be added in subsequent tasks (2.3 - 5.5)
# ---------------------------------------------------------------------------
