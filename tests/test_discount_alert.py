"""Unit tests for DiscountAlert class."""

import pytest

from src.discount_alert import DiscountAlert
from src.models import AppConfig, DiscountAlertResult, ETFConfig, TelegramConfig


@pytest.fixture
def config() -> AppConfig:
    """Minimal AppConfig for testing."""
    return AppConfig(
        etfs=[
            ETFConfig(
                code="513500",
                name="博时标普500ETF",
                target_amount=10000.0,
                bought_amount=0.0,
                premium_rules=[],
                discount_threshold=1.0,
            )
        ],
        telegram=TelegramConfig(enabled=False, bot_token=None, chat_id=None),
        alert_threshold=3.0,
    )


@pytest.fixture
def alert(config: AppConfig) -> DiscountAlert:
    return DiscountAlert(config)


class TestDiscountAlertCheck:
    """Tests for DiscountAlert.check() method."""

    def test_triggers_when_discount_exceeds_threshold(self, alert: DiscountAlert):
        """折价率绝对值 >= 阈值时应触发提醒。"""
        result = alert.check(
            code="513500",
            name="博时标普500ETF",
            premium_rate=-1.5,
            price=1.00,
            iopv=1.015,
            discount_threshold=1.0,
        )
        assert result is not None
        assert isinstance(result, DiscountAlertResult)
        assert result.code == "513500"
        assert result.name == "博时标普500ETF"
        assert result.discount_rate == 1.5
        assert result.price == 1.00
        assert result.iopv == 1.015

    def test_triggers_when_discount_equals_threshold(self, alert: DiscountAlert):
        """折价率绝对值恰好等于阈值时应触发提醒。"""
        result = alert.check(
            code="513500",
            name="博时标普500ETF",
            premium_rate=-2.0,
            price=1.00,
            iopv=1.02,
            discount_threshold=2.0,
        )
        assert result is not None
        assert result.discount_rate == 2.0

    def test_no_trigger_when_discount_below_threshold(self, alert: DiscountAlert):
        """折价率绝对值 < 阈值时不应触发提醒。"""
        result = alert.check(
            code="513500",
            name="博时标普500ETF",
            premium_rate=-0.5,
            price=1.00,
            iopv=1.005,
            discount_threshold=1.0,
        )
        assert result is None

    def test_no_trigger_when_premium_positive(self, alert: DiscountAlert):
        """溢价率为正值时不应触发折价提醒。"""
        result = alert.check(
            code="513500",
            name="博时标普500ETF",
            premium_rate=2.0,
            price=1.02,
            iopv=1.00,
            discount_threshold=1.0,
        )
        assert result is None

    def test_no_trigger_when_premium_zero(self, alert: DiscountAlert):
        """溢价率为零时不应触发折价提醒。"""
        result = alert.check(
            code="513500",
            name="博时标普500ETF",
            premium_rate=0.0,
            price=1.00,
            iopv=1.00,
            discount_threshold=1.0,
        )
        assert result is None

    def test_skip_when_premium_rate_is_none(self, alert: DiscountAlert):
        """premium_rate 为 None 时应跳过检查返回 None。"""
        result = alert.check(
            code="513500",
            name="博时标普500ETF",
            premium_rate=None,
            price=1.00,
            iopv=1.00,
            discount_threshold=1.0,
        )
        assert result is None


class TestDiscountAlertDeduplication:
    """Tests for deduplication within a single run cycle."""

    def test_same_etf_only_alerts_once(self, alert: DiscountAlert):
        """同一 ETF 在同一运行周期内只提醒一次。"""
        result1 = alert.check(
            code="513500",
            name="博时标普500ETF",
            premium_rate=-2.0,
            price=1.00,
            iopv=1.02,
            discount_threshold=1.0,
        )
        result2 = alert.check(
            code="513500",
            name="博时标普500ETF",
            premium_rate=-3.0,
            price=0.97,
            iopv=1.00,
            discount_threshold=1.0,
        )
        assert result1 is not None
        assert result2 is None

    def test_different_etfs_can_both_alert(self, alert: DiscountAlert):
        """不同 ETF 可以各自触发提醒。"""
        result1 = alert.check(
            code="513500",
            name="博时标普500ETF",
            premium_rate=-2.0,
            price=1.00,
            iopv=1.02,
            discount_threshold=1.0,
        )
        result2 = alert.check(
            code="159612",
            name="纳指ETF",
            premium_rate=-1.5,
            price=1.00,
            iopv=1.015,
            discount_threshold=1.0,
        )
        assert result1 is not None
        assert result2 is not None


class TestDiscountAlertReset:
    """Tests for DiscountAlert.reset() method."""

    def test_reset_clears_alerted_codes(self, alert: DiscountAlert):
        """reset() 后同一 ETF 可以再次触发提醒。"""
        # First trigger
        result1 = alert.check(
            code="513500",
            name="博时标普500ETF",
            premium_rate=-2.0,
            price=1.00,
            iopv=1.02,
            discount_threshold=1.0,
        )
        assert result1 is not None

        # Deduplicated
        result2 = alert.check(
            code="513500",
            name="博时标普500ETF",
            premium_rate=-2.0,
            price=1.00,
            iopv=1.02,
            discount_threshold=1.0,
        )
        assert result2 is None

        # Reset and trigger again
        alert.reset()
        result3 = alert.check(
            code="513500",
            name="博时标普500ETF",
            premium_rate=-2.0,
            price=1.00,
            iopv=1.02,
            discount_threshold=1.0,
        )
        assert result3 is not None
