"""Unit tests for premium rate calculation."""

import math

import pytest

from src.models import PremiumRule
from src.premium_calculator import (
    calculate_premium_rate,
    calculate_suggested_buy,
    get_suggestion_text,
)


class TestCalculatePremiumRate:
    """Tests for calculate_premium_rate function."""

    def test_positive_premium(self) -> None:
        """Premium is positive when price > iopv."""
        result = calculate_premium_rate(1.10, 1.00)
        assert result == 10.0

    def test_negative_premium(self) -> None:
        """Premium is negative when price < iopv."""
        result = calculate_premium_rate(0.95, 1.00)
        assert result == -5.0

    def test_zero_premium(self) -> None:
        """Premium is zero when price == iopv."""
        result = calculate_premium_rate(1.00, 1.00)
        assert result == 0.0

    def test_rounds_to_two_decimals(self) -> None:
        """Result is rounded to 2 decimal places."""
        # (1.03 - 1.00) / 1.00 * 100 = 3.0000...04 (floating point)
        result = calculate_premium_rate(1.03, 1.00)
        assert result == 3.0

    def test_realistic_etf_values(self) -> None:
        """Works with realistic ETF price/IOPV values."""
        # 513500 at price 1.856, IOPV 1.800
        result = calculate_premium_rate(1.856, 1.800)
        assert result == 3.11

    def test_price_zero_returns_none(self) -> None:
        """Returns None when price is zero."""
        assert calculate_premium_rate(0, 1.0) is None

    def test_price_negative_returns_none(self) -> None:
        """Returns None when price is negative."""
        assert calculate_premium_rate(-1.5, 1.0) is None

    def test_iopv_zero_returns_none(self) -> None:
        """Returns None when IOPV is zero."""
        assert calculate_premium_rate(1.0, 0) is None

    def test_iopv_negative_returns_none(self) -> None:
        """Returns None when IOPV is negative."""
        assert calculate_premium_rate(1.0, -0.5) is None

    def test_price_nan_returns_none(self) -> None:
        """Returns None when price is NaN."""
        assert calculate_premium_rate(float("nan"), 1.0) is None

    def test_iopv_nan_returns_none(self) -> None:
        """Returns None when IOPV is NaN."""
        assert calculate_premium_rate(1.0, float("nan")) is None

    def test_price_inf_returns_none(self) -> None:
        """Returns None when price is infinity."""
        assert calculate_premium_rate(float("inf"), 1.0) is None

    def test_iopv_inf_returns_none(self) -> None:
        """Returns None when IOPV is infinity."""
        assert calculate_premium_rate(1.0, float("inf")) is None

    def test_invalid_type_price_returns_none(self) -> None:
        """Returns None when price is not a number."""
        assert calculate_premium_rate("abc", 1.0) is None  # type: ignore[arg-type]

    def test_invalid_type_iopv_returns_none(self) -> None:
        """Returns None when IOPV is not a number."""
        assert calculate_premium_rate(1.0, None) is None  # type: ignore[arg-type]

    def test_int_inputs_accepted(self) -> None:
        """Accepts integer inputs (int is a valid numeric type)."""
        result = calculate_premium_rate(2, 1)
        assert result == 100.0


class TestCalculateSuggestedBuy:
    """Tests for calculate_suggested_buy function."""

    @pytest.fixture
    def rules_513500(self) -> list[PremiumRule]:
        """Standard rules for 513500."""
        return [
            PremiumRule(max_premium=1.0, min_ratio=0.6, max_ratio=1.0),
            PremiumRule(max_premium=3.0, min_ratio=0.3, max_ratio=0.5),
            PremiumRule(max_premium=5.0, min_ratio=0.1, max_ratio=0.2),
        ]

    def test_rate_within_first_bracket(self, rules_513500: list[PremiumRule]) -> None:
        """Rate <= 1.0 uses first rule (60%-100%)."""
        result = calculate_suggested_buy(0.5, 70000.0, rules_513500)
        assert result == (42000, 70000)

    def test_rate_at_first_boundary(self, rules_513500: list[PremiumRule]) -> None:
        """Rate exactly 1.0 uses first rule."""
        result = calculate_suggested_buy(1.0, 70000.0, rules_513500)
        assert result == (42000, 70000)

    def test_rate_within_second_bracket(self, rules_513500: list[PremiumRule]) -> None:
        """1.0 < rate <= 3.0 uses second rule (30%-50%)."""
        result = calculate_suggested_buy(2.0, 70000.0, rules_513500)
        assert result == (21000, 35000)

    def test_rate_within_third_bracket(self, rules_513500: list[PremiumRule]) -> None:
        """3.0 < rate <= 5.0 uses third rule (10%-20%)."""
        result = calculate_suggested_buy(4.0, 70000.0, rules_513500)
        assert result == (7000, 14000)

    def test_rate_exceeds_all_rules(self, rules_513500: list[PremiumRule]) -> None:
        """Rate >= 5.0 returns (0, 0)."""
        result = calculate_suggested_buy(5.1, 70000.0, rules_513500)
        assert result == (0, 0)

    def test_rate_exactly_at_max_boundary(self, rules_513500: list[PremiumRule]) -> None:
        """Rate exactly at last rule boundary (5.0) uses that rule."""
        result = calculate_suggested_buy(5.0, 70000.0, rules_513500)
        assert result == (7000, 14000)

    def test_remaining_target_zero(self, rules_513500: list[PremiumRule]) -> None:
        """When remaining_target is 0, calculation still runs, result is (0, 0)."""
        result = calculate_suggested_buy(0.5, 0.0, rules_513500)
        assert result == (0, 0)

    def test_result_is_truncated_int(self) -> None:
        """Results are truncated to int (not rounded)."""
        rules = [PremiumRule(max_premium=1.0, min_ratio=0.6, max_ratio=1.0)]
        # 0.6 * 999 = 599.4 -> int(599.4) = 599
        result = calculate_suggested_buy(0.5, 999.0, rules)
        assert result == (599, 999)

    def test_returns_int_types(self, rules_513500: list[PremiumRule]) -> None:
        """Both values in the tuple are Python int types."""
        result = calculate_suggested_buy(0.5, 70000.0, rules_513500)
        assert isinstance(result[0], int)
        assert isinstance(result[1], int)

    def test_empty_rules_returns_zero(self) -> None:
        """Empty rules list returns (0, 0)."""
        result = calculate_suggested_buy(0.5, 70000.0, [])
        assert result == (0, 0)

    def test_unsorted_rules_still_works(self) -> None:
        """Rules not sorted by max_premium are sorted internally."""
        rules = [
            PremiumRule(max_premium=5.0, min_ratio=0.1, max_ratio=0.2),
            PremiumRule(max_premium=1.0, min_ratio=0.6, max_ratio=1.0),
            PremiumRule(max_premium=3.0, min_ratio=0.3, max_ratio=0.5),
        ]
        result = calculate_suggested_buy(0.5, 70000.0, rules)
        assert result == (42000, 70000)


class TestGetSuggestionText:
    """Tests for get_suggestion_text function."""

    def test_rate_below_one(self) -> None:
        """Rate < 1.0 returns '可以买入'."""
        assert get_suggestion_text(0.5) == "可以买入"

    def test_rate_exactly_one(self) -> None:
        """Rate == 1.0 returns '可以买入'."""
        assert get_suggestion_text(1.0) == "可以买入"

    def test_rate_between_one_and_five(self) -> None:
        """1.0 < rate < 5.0 returns '可以分批买'."""
        assert get_suggestion_text(3.0) == "可以分批买"

    def test_rate_just_above_one(self) -> None:
        """Rate just above 1.0 returns '可以分批买'."""
        assert get_suggestion_text(1.01) == "可以分批买"

    def test_rate_just_below_five(self) -> None:
        """Rate just below 5.0 returns '可以分批买'."""
        assert get_suggestion_text(4.99) == "可以分批买"

    def test_rate_exactly_five(self) -> None:
        """Rate == 5.0 returns '不建议买'."""
        assert get_suggestion_text(5.0) == "不建议买"

    def test_rate_above_five(self) -> None:
        """Rate > 5.0 returns '不建议买'."""
        assert get_suggestion_text(10.0) == "不建议买"

    def test_negative_rate(self) -> None:
        """Negative rate (discount) returns '可以买入'."""
        assert get_suggestion_text(-2.0) == "可以买入"
