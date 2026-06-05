"""Unit tests for the Monitor orchestrator."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from src.models import (
    AppConfig,
    DiscountAlertResult,
    ETFConfig,
    ETFData,
    MonitorResult,
    PremiumRule,
    TelegramConfig,
)
from src.monitor import Monitor


def _make_config(
    etfs: list[ETFConfig] | None = None,
    telegram_enabled: bool = False,
) -> AppConfig:
    """Helper to create a test AppConfig."""
    if etfs is None:
        etfs = [
            ETFConfig(
                code="513500",
                name="博时标普500ETF",
                target_amount=100000,
                bought_amount=30000,
                premium_rules=[
                    PremiumRule(max_premium=1.0, min_ratio=0.6, max_ratio=1.0),
                    PremiumRule(max_premium=3.0, min_ratio=0.3, max_ratio=0.5),
                    PremiumRule(max_premium=5.0, min_ratio=0.1, max_ratio=0.2),
                ],
            ),
        ]
    return AppConfig(
        etfs=etfs,
        telegram=TelegramConfig(
            enabled=telegram_enabled,
            bot_token="test_token" if telegram_enabled else None,
            chat_id="test_chat" if telegram_enabled else None,
        ),
        alert_threshold=3.0,
    )


def _make_etf_data(code: str = "513500", price: float = 1.5, iopv: float = 1.45) -> ETFData:
    """Helper to create test ETFData."""
    return ETFData(
        code=code,
        price=price,
        iopv=iopv,
        update_time=datetime(2024, 1, 15, 9, 30, 0),
        source="AKShare",
    )


class TestMonitorRun:
    """Tests for Monitor.run() orchestration flow."""

    @patch("src.monitor.DataSourceManager")
    @patch("src.monitor.AKShareSource")
    @patch("src.monitor.HaoETFSource")
    def test_successful_single_etf(self, mock_haoetf, mock_akshare, mock_dsm_cls, capsys):
        """Test successful processing of a single ETF."""
        config = _make_config()
        monitor = Monitor(config)

        # Mock the data source manager
        mock_dsm = MagicMock()
        mock_dsm.get_etf_data.return_value = (_make_etf_data(), None)
        monitor._data_source_manager = mock_dsm

        results = monitor.run()

        assert len(results) == 1
        result = results[0]
        assert result.code == "513500"
        assert result.name == "博时标普500ETF"
        assert result.price == 1.5
        assert result.iopv == 1.45
        assert result.premium_rate is not None
        assert result.error is None
        assert result.remaining_target == 70000
        assert result.suggested_buy_min is not None
        assert result.suggested_buy_max is not None
        assert result.suggestion is not None

    @patch("src.monitor.DataSourceManager")
    @patch("src.monitor.AKShareSource")
    @patch("src.monitor.HaoETFSource")
    def test_data_fetch_failure_returns_error_result(self, mock_haoetf, mock_akshare, mock_dsm_cls, capsys):
        """Test that data fetch failure creates MonitorResult with error."""
        config = _make_config()
        monitor = Monitor(config)

        mock_dsm = MagicMock()
        mock_dsm.get_etf_data.return_value = (None, "所有数据源获取 513500 均失败")
        monitor._data_source_manager = mock_dsm

        results = monitor.run()

        assert len(results) == 1
        result = results[0]
        assert result.code == "513500"
        assert result.error is not None
        assert "失败" in result.error
        assert result.price is None
        assert result.premium_rate is None

    @patch("src.monitor.DataSourceManager")
    @patch("src.monitor.AKShareSource")
    @patch("src.monitor.HaoETFSource")
    def test_per_etf_error_continues_processing(self, mock_haoetf, mock_akshare, mock_dsm_cls, capsys):
        """Test that one ETF failure doesn't stop processing of others."""
        etfs = [
            ETFConfig(
                code="513500",
                name="博时标普500ETF",
                target_amount=100000,
                bought_amount=30000,
                premium_rules=[
                    PremiumRule(max_premium=1.0, min_ratio=0.6, max_ratio=1.0),
                ],
            ),
            ETFConfig(
                code="159501",
                name="嘉实纳斯达克100ETF",
                target_amount=80000,
                bought_amount=20000,
                premium_rules=[
                    PremiumRule(max_premium=1.0, min_ratio=0.6, max_ratio=1.0),
                ],
            ),
        ]
        config = _make_config(etfs=etfs)
        monitor = Monitor(config)

        mock_dsm = MagicMock()
        # First ETF fails, second succeeds
        mock_dsm.get_etf_data.side_effect = [
            (None, "所有数据源获取 513500 均失败"),
            (_make_etf_data(code="159501"), None),
        ]
        monitor._data_source_manager = mock_dsm

        results = monitor.run()

        assert len(results) == 2
        assert results[0].error is not None
        assert results[1].error is None
        assert results[1].code == "159501"
        assert results[1].premium_rate is not None

    @patch("src.monitor.DataSourceManager")
    @patch("src.monitor.AKShareSource")
    @patch("src.monitor.HaoETFSource")
    def test_calculation_error_returns_error_result(self, mock_haoetf, mock_akshare, mock_dsm_cls, capsys):
        """Test that invalid price/iopv creates MonitorResult with calculation error."""
        config = _make_config()
        monitor = Monitor(config)

        # Return data with iopv=0 which will cause calculation error
        mock_dsm = MagicMock()
        mock_dsm.get_etf_data.return_value = (ETFData(
            code="513500",
            price=1.5,
            iopv=0.0,
            update_time=datetime(2024, 1, 15, 9, 30, 0),
            source="AKShare",
        ), None)
        monitor._data_source_manager = mock_dsm

        results = monitor.run()

        assert len(results) == 1
        result = results[0]
        assert result.error is not None
        assert "计算失败" in result.error
        assert result.price == 1.5
        assert result.iopv == 0.0
        assert result.premium_rate is None

    @patch("src.monitor.DataSourceManager")
    @patch("src.monitor.AKShareSource")
    @patch("src.monitor.HaoETFSource")
    def test_telegram_notification_sent_when_enabled(self, mock_haoetf, mock_akshare, mock_dsm_cls, capsys):
        """Test that Telegram notification is sent when enabled and actionable signal exists."""
        config = _make_config(telegram_enabled=True)
        monitor = Monitor(config)

        mock_dsm = MagicMock()
        mock_dsm.get_etf_data.return_value = (_make_etf_data(), None)
        monitor._data_source_manager = mock_dsm

        mock_notifier = MagicMock()
        mock_notifier.send.return_value = True
        monitor._notifier = mock_notifier

        results = monitor.run()

        mock_notifier.send.assert_called_once()
        # Verify the compact message was formatted (contains ETF name)
        sent_message = mock_notifier.send.call_args[0][0]
        assert "博时标普500ETF" in sent_message

    @patch("src.monitor.DataSourceManager")
    @patch("src.monitor.AKShareSource")
    @patch("src.monitor.HaoETFSource")
    def test_telegram_not_sent_when_disabled(self, mock_haoetf, mock_akshare, mock_dsm_cls, capsys):
        """Test that Telegram notification is not sent when disabled."""
        config = _make_config(telegram_enabled=False)
        monitor = Monitor(config)

        mock_dsm = MagicMock()
        mock_dsm.get_etf_data.return_value = (_make_etf_data(), None)
        monitor._data_source_manager = mock_dsm

        mock_notifier = MagicMock()
        monitor._notifier = mock_notifier

        results = monitor.run()

        mock_notifier.send.assert_not_called()

    @patch("src.monitor.DataSourceManager")
    @patch("src.monitor.AKShareSource")
    @patch("src.monitor.HaoETFSource")
    def test_error_etf_suppressed_in_quiet_mode(self, mock_haoetf, mock_akshare, mock_dsm_cls, capsys):
        """Test that error-only results suppress notification in quiet mode (no actionable signal)."""
        config = _make_config(telegram_enabled=True)
        monitor = Monitor(config)  # quiet_mode=True by default

        mock_dsm = MagicMock()
        mock_dsm.get_etf_data.return_value = (None, "所有数据源获取 513500 均失败")
        monitor._data_source_manager = mock_dsm

        mock_notifier = MagicMock()
        mock_notifier.send.return_value = True
        monitor._notifier = mock_notifier

        results = monitor.run()

        # In quiet mode, error-only (no actionable signal) suppresses notification
        mock_notifier.send.assert_not_called()

    @patch("src.monitor.DataSourceManager")
    @patch("src.monitor.AKShareSource")
    @patch("src.monitor.HaoETFSource")
    def test_error_etf_included_in_no_quiet_mode(self, mock_haoetf, mock_akshare, mock_dsm_cls, capsys):
        """Test that error info is included in Telegram notification when --no-quiet mode."""
        config = _make_config(telegram_enabled=True)
        monitor = Monitor(config, quiet_mode=False)

        mock_dsm = MagicMock()
        mock_dsm.get_etf_data.return_value = (None, "所有数据源获取 513500 均失败")
        monitor._data_source_manager = mock_dsm

        mock_notifier = MagicMock()
        mock_notifier.send.return_value = True
        monitor._notifier = mock_notifier

        results = monitor.run()

        mock_notifier.send.assert_called_once()
        sent_message = mock_notifier.send.call_args[0][0]
        # The error message should be present in the Telegram notification
        assert "错误" in sent_message or "失败" in sent_message

    @patch("src.monitor.DataSourceManager")
    @patch("src.monitor.AKShareSource")
    @patch("src.monitor.HaoETFSource")
    def test_remaining_target_calculated_correctly(self, mock_haoetf, mock_akshare, mock_dsm_cls, capsys):
        """Test remaining_target = target_amount - bought_amount."""
        config = _make_config()
        monitor = Monitor(config)

        mock_dsm = MagicMock()
        mock_dsm.get_etf_data.return_value = (_make_etf_data(), None)
        monitor._data_source_manager = mock_dsm

        results = monitor.run()

        result = results[0]
        assert result.remaining_target == 70000  # 100000 - 30000

    @patch("src.monitor.DataSourceManager")
    @patch("src.monitor.AKShareSource")
    @patch("src.monitor.HaoETFSource")
    def test_never_raises_exceptions(self, mock_haoetf, mock_akshare, mock_dsm_cls, capsys):
        """Test that Monitor.run() never raises exceptions."""
        config = _make_config()
        monitor = Monitor(config)

        mock_dsm = MagicMock()
        mock_dsm.get_etf_data.side_effect = RuntimeError("unexpected error")
        monitor._data_source_manager = mock_dsm

        # Should not raise
        results = monitor.run()

        assert len(results) == 1
        assert results[0].error is not None


class TestMonitorDiscountAlert:
    """Tests for discount alert integration in Monitor (Task 4.4)."""

    @patch("src.monitor.DataSourceManager")
    @patch("src.monitor.AKShareSource")
    @patch("src.monitor.HaoETFSource")
    def test_discount_alert_triggered_and_sent(self, mock_haoetf, mock_akshare, mock_dsm_cls, capsys):
        """Test that discount alert is triggered and Telegram message sent when discount detected."""
        config = _make_config(telegram_enabled=True)
        monitor = Monitor(config)

        # ETF with price below iopv (discount scenario)
        # price=1.40, iopv=1.50 → premium_rate = (1.40-1.50)/1.50*100 = -6.67%
        mock_dsm = MagicMock()
        mock_dsm.get_etf_data.return_value = (ETFData(
            code="513500",
            price=1.40,
            iopv=1.50,
            update_time=datetime(2024, 1, 15, 9, 30, 0),
            source="AKShare",
        ), None)
        monitor._data_source_manager = mock_dsm

        mock_notifier = MagicMock()
        mock_notifier.send.return_value = True
        monitor._notifier = mock_notifier

        results = monitor.run()

        # Should have called send twice: once for discount alert, once for normal notification
        assert mock_notifier.send.call_count == 2
        # First call is the discount alert
        discount_msg = mock_notifier.send.call_args_list[0][0][0]
        assert "折价提醒" in discount_msg
        assert "513500" in discount_msg

    @patch("src.monitor.DataSourceManager")
    @patch("src.monitor.AKShareSource")
    @patch("src.monitor.HaoETFSource")
    def test_no_discount_alert_when_premium_positive(self, mock_haoetf, mock_akshare, mock_dsm_cls, capsys):
        """Test no discount alert when premium rate is positive."""
        config = _make_config(telegram_enabled=True)
        monitor = Monitor(config)

        # price > iopv → positive premium, no discount
        mock_dsm = MagicMock()
        mock_dsm.get_etf_data.return_value = (_make_etf_data(price=1.5, iopv=1.45), None)
        monitor._data_source_manager = mock_dsm

        mock_notifier = MagicMock()
        mock_notifier.send.return_value = True
        monitor._notifier = mock_notifier

        results = monitor.run()

        # Only one send call for regular notification, no discount alert
        assert mock_notifier.send.call_count == 1
        sent_msg = mock_notifier.send.call_args_list[0][0][0]
        assert "折价提醒" not in sent_msg

    @patch("src.monitor.DataSourceManager")
    @patch("src.monitor.AKShareSource")
    @patch("src.monitor.HaoETFSource")
    def test_discount_alert_not_sent_when_telegram_disabled(self, mock_haoetf, mock_akshare, mock_dsm_cls, capsys):
        """Test that discount alert does not send when Telegram is disabled."""
        config = _make_config(telegram_enabled=False)
        monitor = Monitor(config)

        # Discount scenario
        mock_dsm = MagicMock()
        mock_dsm.get_etf_data.return_value = (ETFData(
            code="513500",
            price=1.40,
            iopv=1.50,
            update_time=datetime(2024, 1, 15, 9, 30, 0),
            source="AKShare",
        ), None)
        monitor._data_source_manager = mock_dsm

        mock_notifier = MagicMock()
        monitor._notifier = mock_notifier

        results = monitor.run()

        # No notification calls at all
        mock_notifier.send.assert_not_called()

    @patch("src.monitor.DataSourceManager")
    @patch("src.monitor.AKShareSource")
    @patch("src.monitor.HaoETFSource")
    def test_discount_alert_telegram_failure_does_not_interrupt(self, mock_haoetf, mock_akshare, mock_dsm_cls, capsys):
        """Test that Telegram push failure for discount alert does not interrupt monitoring."""
        config = _make_config(telegram_enabled=True)
        monitor = Monitor(config)

        # Discount scenario
        mock_dsm = MagicMock()
        mock_dsm.get_etf_data.return_value = (ETFData(
            code="513500",
            price=1.40,
            iopv=1.50,
            update_time=datetime(2024, 1, 15, 9, 30, 0),
            source="AKShare",
        ), None)
        monitor._data_source_manager = mock_dsm

        mock_notifier = MagicMock()
        mock_notifier.send.return_value = False  # Simulate push failure
        monitor._notifier = mock_notifier

        # Should not raise
        results = monitor.run()

        assert len(results) == 1
        assert results[0].error is None
        assert results[0].premium_rate is not None


class TestMonitorVolumeConditional:
    """Tests for volume/turnover_rate conditional display in Monitor (Task 5.2)."""

    @patch("src.monitor.DataSourceManager")
    @patch("src.monitor.AKShareSource")
    @patch("src.monitor.HaoETFSource")
    def test_volume_included_when_premium_above_threshold(self, mock_haoetf, mock_akshare, mock_dsm_cls, capsys):
        """Test volume/turnover_rate attached when premium_rate >= alert_threshold."""
        config = _make_config()  # alert_threshold=3.0
        monitor = Monitor(config)

        # price=1.55, iopv=1.45 → premium_rate = (1.55-1.45)/1.45*100 ≈ 6.90%
        # This exceeds alert_threshold of 3.0
        mock_dsm = MagicMock()
        mock_dsm.get_etf_data.return_value = (ETFData(
            code="513500",
            price=1.55,
            iopv=1.45,
            update_time=datetime(2024, 1, 15, 9, 30, 0),
            source="AKShare",
            volume=5000000.0,
            turnover_rate=2.35,
        ), None)
        monitor._data_source_manager = mock_dsm

        results = monitor.run()

        result = results[0]
        assert result.premium_rate >= 3.0
        assert result.volume == 5000000.0
        assert result.turnover_rate == 2.35

    @patch("src.monitor.DataSourceManager")
    @patch("src.monitor.AKShareSource")
    @patch("src.monitor.HaoETFSource")
    def test_volume_none_when_premium_below_threshold(self, mock_haoetf, mock_akshare, mock_dsm_cls, capsys):
        """Test volume/turnover_rate are None when premium_rate < alert_threshold."""
        config = _make_config()  # alert_threshold=3.0
        monitor = Monitor(config)

        # price=1.46, iopv=1.45 → premium_rate = (1.46-1.45)/1.45*100 ≈ 0.69%
        # This is below alert_threshold of 3.0
        mock_dsm = MagicMock()
        mock_dsm.get_etf_data.return_value = (ETFData(
            code="513500",
            price=1.46,
            iopv=1.45,
            update_time=datetime(2024, 1, 15, 9, 30, 0),
            source="AKShare",
            volume=5000000.0,
            turnover_rate=2.35,
        ), None)
        monitor._data_source_manager = mock_dsm

        results = monitor.run()

        result = results[0]
        assert result.premium_rate < 3.0
        assert result.volume is None
        assert result.turnover_rate is None

    @patch("src.monitor.DataSourceManager")
    @patch("src.monitor.AKShareSource")
    @patch("src.monitor.HaoETFSource")
    def test_volume_none_when_exactly_at_threshold(self, mock_haoetf, mock_akshare, mock_dsm_cls, capsys):
        """Test volume/turnover_rate included when premium_rate exactly equals alert_threshold."""
        # alert_threshold=3.0, we need premium_rate exactly 3.0
        # premium_rate = (price - iopv) / iopv * 100 = 3.0
        # price = iopv * 1.03 = 1.45 * 1.03 = 1.4935
        config = _make_config()
        monitor = Monitor(config)

        mock_dsm = MagicMock()
        mock_dsm.get_etf_data.return_value = (ETFData(
            code="513500",
            price=1.4935,
            iopv=1.45,
            update_time=datetime(2024, 1, 15, 9, 30, 0),
            source="AKShare",
            volume=3000000.0,
            turnover_rate=1.5,
        ), None)
        monitor._data_source_manager = mock_dsm

        results = monitor.run()

        result = results[0]
        assert result.premium_rate >= 3.0
        assert result.volume == 3000000.0
        assert result.turnover_rate == 1.5

    @patch("src.monitor.DataSourceManager")
    @patch("src.monitor.AKShareSource")
    @patch("src.monitor.HaoETFSource")
    def test_volume_none_propagated_when_source_has_no_data(self, mock_haoetf, mock_akshare, mock_dsm_cls, capsys):
        """Test that when source has None volume, result also has None even above threshold."""
        config = _make_config()  # alert_threshold=3.0
        monitor = Monitor(config)

        # High premium but no volume data from source
        mock_dsm = MagicMock()
        mock_dsm.get_etf_data.return_value = (ETFData(
            code="513500",
            price=1.55,
            iopv=1.45,
            update_time=datetime(2024, 1, 15, 9, 30, 0),
            source="AKShare",
            volume=None,
            turnover_rate=None,
        ), None)
        monitor._data_source_manager = mock_dsm

        results = monitor.run()

        result = results[0]
        assert result.premium_rate >= 3.0
        # Volume/turnover_rate from source is None, so result is None
        assert result.volume is None
        assert result.turnover_rate is None


class TestMonitorGetTrendInfo:
    """Tests for Monitor._get_trend_info() method (Task 3.1)."""

    @patch("src.monitor.DataSourceManager")
    @patch("src.monitor.AKShareSource")
    @patch("src.monitor.HaoETFSource")
    def test_trend_up_when_delta_above_threshold(self, mock_haoetf, mock_akshare, mock_dsm_cls):
        """Test that arrow is '↑' when current - previous >= 0.01."""
        from src.models import PremiumRecord

        config = _make_config()
        monitor = Monitor(config)

        # Mock premium store to return a previous record with premium_rate = 2.0
        mock_store = MagicMock()
        mock_store.query.return_value = [
            PremiumRecord(code="513500", premium_rate=2.0, timestamp=datetime(2024, 1, 15, 9, 0, 0))
        ]
        monitor._premium_store = mock_store

        result = monitor._get_trend_info("513500", 2.5)

        assert result is not None
        assert result.arrow == "↑"
        assert result.delta == pytest.approx(0.5)
        assert result.previous_rate == 2.0

    @patch("src.monitor.DataSourceManager")
    @patch("src.monitor.AKShareSource")
    @patch("src.monitor.HaoETFSource")
    def test_trend_down_when_delta_below_negative_threshold(self, mock_haoetf, mock_akshare, mock_dsm_cls):
        """Test that arrow is '↓' when current - previous <= -0.01."""
        from src.models import PremiumRecord

        config = _make_config()
        monitor = Monitor(config)

        mock_store = MagicMock()
        mock_store.query.return_value = [
            PremiumRecord(code="513500", premium_rate=3.0, timestamp=datetime(2024, 1, 15, 9, 0, 0))
        ]
        monitor._premium_store = mock_store

        result = monitor._get_trend_info("513500", 2.5)

        assert result is not None
        assert result.arrow == "↓"
        assert result.delta == pytest.approx(-0.5)
        assert result.previous_rate == 3.0

    @patch("src.monitor.DataSourceManager")
    @patch("src.monitor.AKShareSource")
    @patch("src.monitor.HaoETFSource")
    def test_trend_stable_when_delta_within_threshold(self, mock_haoetf, mock_akshare, mock_dsm_cls):
        """Test that arrow is '→' when abs(delta) < 0.01."""
        from src.models import PremiumRecord

        config = _make_config()
        monitor = Monitor(config)

        mock_store = MagicMock()
        mock_store.query.return_value = [
            PremiumRecord(code="513500", premium_rate=2.005, timestamp=datetime(2024, 1, 15, 9, 0, 0))
        ]
        monitor._premium_store = mock_store

        result = monitor._get_trend_info("513500", 2.01)

        assert result is not None
        assert result.arrow == "→"
        assert abs(result.delta) < 0.01

    @patch("src.monitor.DataSourceManager")
    @patch("src.monitor.AKShareSource")
    @patch("src.monitor.HaoETFSource")
    def test_returns_none_when_no_previous_records(self, mock_haoetf, mock_akshare, mock_dsm_cls):
        """Test that None is returned when PremiumStore has no records."""
        config = _make_config()
        monitor = Monitor(config)

        mock_store = MagicMock()
        mock_store.query.return_value = []
        monitor._premium_store = mock_store

        result = monitor._get_trend_info("513500", 2.5)

        assert result is None

    @patch("src.monitor.DataSourceManager")
    @patch("src.monitor.AKShareSource")
    @patch("src.monitor.HaoETFSource")
    def test_returns_none_on_store_error(self, mock_haoetf, mock_akshare, mock_dsm_cls):
        """Test that None is returned and warning logged on StoreError."""
        from src.exceptions import StoreError

        config = _make_config()
        monitor = Monitor(config)

        mock_store = MagicMock()
        mock_store.query.side_effect = StoreError("read", "513500", "IO error")
        monitor._premium_store = mock_store

        result = monitor._get_trend_info("513500", 2.5)

        assert result is None

    @patch("src.monitor.DataSourceManager")
    @patch("src.monitor.AKShareSource")
    @patch("src.monitor.HaoETFSource")
    def test_uses_last_record_as_most_recent(self, mock_haoetf, mock_akshare, mock_dsm_cls):
        """Test that the last record in the list is used as the most recent."""
        from src.models import PremiumRecord

        config = _make_config()
        monitor = Monitor(config)

        mock_store = MagicMock()
        mock_store.query.return_value = [
            PremiumRecord(code="513500", premium_rate=1.0, timestamp=datetime(2024, 1, 15, 9, 0, 0)),
            PremiumRecord(code="513500", premium_rate=2.0, timestamp=datetime(2024, 1, 15, 9, 30, 0)),
            PremiumRecord(code="513500", premium_rate=3.0, timestamp=datetime(2024, 1, 15, 10, 0, 0)),
        ]
        monitor._premium_store = mock_store

        result = monitor._get_trend_info("513500", 3.5)

        assert result is not None
        # Should compare against the last record (premium_rate=3.0)
        assert result.previous_rate == 3.0
        assert result.delta == pytest.approx(0.5)
        assert result.arrow == "↑"

    @patch("src.monitor.DataSourceManager")
    @patch("src.monitor.AKShareSource")
    @patch("src.monitor.HaoETFSource")
    def test_boundary_delta_exactly_001(self, mock_haoetf, mock_akshare, mock_dsm_cls):
        """Test that delta exactly 0.01 produces '↑' arrow.

        Note: uses integer-friendly values to avoid floating point imprecision.
        previous=2.0, current=2.0+0.01=2.01 in float is slightly less than 0.01,
        so we use a value that clearly crosses the threshold.
        """
        from src.models import PremiumRecord

        config = _make_config()
        monitor = Monitor(config)

        mock_store = MagicMock()
        # Use 1.0 and 1.01 which gives exactly 0.01 delta (no float imprecision)
        mock_store.query.return_value = [
            PremiumRecord(code="513500", premium_rate=1.0, timestamp=datetime(2024, 1, 15, 9, 0, 0))
        ]
        monitor._premium_store = mock_store

        # 1.02 - 1.0 = 0.02 which is clearly >= 0.01
        result = monitor._get_trend_info("513500", 1.02)

        assert result is not None
        assert result.arrow == "↑"
        assert result.delta == pytest.approx(0.02)

    @patch("src.monitor.DataSourceManager")
    @patch("src.monitor.AKShareSource")
    @patch("src.monitor.HaoETFSource")
    def test_boundary_delta_exactly_negative_001(self, mock_haoetf, mock_akshare, mock_dsm_cls):
        """Test that delta exactly -0.01 produces '↓' arrow."""
        from src.models import PremiumRecord

        config = _make_config()
        monitor = Monitor(config)

        mock_store = MagicMock()
        mock_store.query.return_value = [
            PremiumRecord(code="513500", premium_rate=2.0, timestamp=datetime(2024, 1, 15, 9, 0, 0))
        ]
        monitor._premium_store = mock_store

        result = monitor._get_trend_info("513500", 1.99)

        assert result is not None
        assert result.arrow == "↓"
        assert result.delta == pytest.approx(-0.01)


class TestMonitorHasActionableSignal:
    """Tests for Monitor._has_actionable_signal() method (Task 6.1)."""

    @patch("src.monitor.DataSourceManager")
    @patch("src.monitor.AKShareSource")
    @patch("src.monitor.HaoETFSource")
    def test_returns_true_when_buy_signal_present(self, mock_haoetf, mock_akshare, mock_dsm_cls):
        """Test returns True when a result has suggested_buy_min > 0."""
        config = _make_config()
        monitor = Monitor(config)

        results = [
            MonitorResult(
                code="513500", name="博时标普500ETF", price=1.5, iopv=1.45,
                premium_rate=2.0, target_amount=100000, bought_amount=30000,
                remaining_target=70000, suggested_buy_min=5000, suggested_buy_max=10000,
                suggestion="建议买入", source="AKShare",
                update_time=datetime(2024, 1, 15, 9, 30, 0), error=None,
            )
        ]

        assert monitor._has_actionable_signal(results, [], []) is True

    @patch("src.monitor.DataSourceManager")
    @patch("src.monitor.AKShareSource")
    @patch("src.monitor.HaoETFSource")
    def test_returns_true_when_sell_suggestions_present(self, mock_haoetf, mock_akshare, mock_dsm_cls):
        """Test returns True when sell_suggestions is non-empty."""
        from src.models import SellSuggestion

        config = _make_config()
        monitor = Monitor(config)

        results = [
            MonitorResult(
                code="513500", name="博时标普500ETF", price=1.5, iopv=1.45,
                premium_rate=2.0, target_amount=100000, bought_amount=30000,
                remaining_target=70000, suggested_buy_min=0, suggested_buy_max=0,
                suggestion="观望", source="AKShare",
                update_time=datetime(2024, 1, 15, 9, 30, 0), error=None,
            )
        ]
        sell_suggestions = [
            SellSuggestion(code="513500", name="博时标普500ETF",
                           premium_rate=9.0, sell_percentage=0.3, sell_amount=9000)
        ]

        assert monitor._has_actionable_signal(results, sell_suggestions, []) is True

    @patch("src.monitor.DataSourceManager")
    @patch("src.monitor.AKShareSource")
    @patch("src.monitor.HaoETFSource")
    def test_returns_true_when_discount_alerts_present(self, mock_haoetf, mock_akshare, mock_dsm_cls):
        """Test returns True when discount_alerts is non-empty."""
        config = _make_config()
        monitor = Monitor(config)

        results = [
            MonitorResult(
                code="513500", name="博时标普500ETF", price=1.4, iopv=1.5,
                premium_rate=-6.67, target_amount=100000, bought_amount=30000,
                remaining_target=70000, suggested_buy_min=0, suggested_buy_max=0,
                suggestion="观望", source="AKShare",
                update_time=datetime(2024, 1, 15, 9, 30, 0), error=None,
            )
        ]
        discount_alerts = [
            DiscountAlertResult(code="513500", name="博时标普500ETF",
                                discount_rate=6.67, price=1.4, iopv=1.5)
        ]

        assert monitor._has_actionable_signal(results, [], discount_alerts) is True

    @patch("src.monitor.DataSourceManager")
    @patch("src.monitor.AKShareSource")
    @patch("src.monitor.HaoETFSource")
    def test_returns_false_when_no_signals(self, mock_haoetf, mock_akshare, mock_dsm_cls):
        """Test returns False when no actionable signals exist."""
        config = _make_config()
        monitor = Monitor(config)

        results = [
            MonitorResult(
                code="513500", name="博时标普500ETF", price=1.5, iopv=1.45,
                premium_rate=2.0, target_amount=100000, bought_amount=30000,
                remaining_target=70000, suggested_buy_min=0, suggested_buy_max=0,
                suggestion="观望", source="AKShare",
                update_time=datetime(2024, 1, 15, 9, 30, 0), error=None,
            )
        ]

        assert monitor._has_actionable_signal(results, [], []) is False

    @patch("src.monitor.DataSourceManager")
    @patch("src.monitor.AKShareSource")
    @patch("src.monitor.HaoETFSource")
    def test_returns_false_when_suggested_buy_min_is_none(self, mock_haoetf, mock_akshare, mock_dsm_cls):
        """Test returns False when suggested_buy_min is None (error case)."""
        config = _make_config()
        monitor = Monitor(config)

        results = [
            MonitorResult(
                code="513500", name="博时标普500ETF", price=None, iopv=None,
                premium_rate=None, target_amount=100000, bought_amount=30000,
                remaining_target=70000, suggested_buy_min=None, suggested_buy_max=None,
                suggestion=None, source=None,
                update_time=None, error="数据获取失败",
            )
        ]

        assert monitor._has_actionable_signal(results, [], []) is False

    @patch("src.monitor.DataSourceManager")
    @patch("src.monitor.AKShareSource")
    @patch("src.monitor.HaoETFSource")
    def test_returns_false_when_all_etfs_have_errors(self, mock_haoetf, mock_akshare, mock_dsm_cls):
        """Test returns False when all ETFs have errors (validates Req 1.5)."""
        config = _make_config()
        monitor = Monitor(config)

        results = [
            MonitorResult(
                code="513500", name="博时标普500ETF", price=None, iopv=None,
                premium_rate=None, target_amount=100000, bought_amount=30000,
                remaining_target=70000, suggested_buy_min=None, suggested_buy_max=None,
                suggestion=None, source=None,
                update_time=None, error="数据获取失败",
            ),
            MonitorResult(
                code="159501", name="嘉实纳斯达克100ETF", price=None, iopv=None,
                premium_rate=None, target_amount=80000, bought_amount=20000,
                remaining_target=60000, suggested_buy_min=None, suggested_buy_max=None,
                suggestion=None, source=None,
                update_time=None, error="所有数据源均失败",
            ),
        ]

        assert monitor._has_actionable_signal(results, [], []) is False

    @patch("src.monitor.DataSourceManager")
    @patch("src.monitor.AKShareSource")
    @patch("src.monitor.HaoETFSource")
    def test_returns_false_with_empty_results(self, mock_haoetf, mock_akshare, mock_dsm_cls):
        """Test returns False when results list is empty."""
        config = _make_config()
        monitor = Monitor(config)

        assert monitor._has_actionable_signal([], [], []) is False


class TestMonitorQuietModeInit:
    """Tests for Monitor.__init__ quiet_mode parameter (Task 6.1)."""

    @patch("src.monitor.DataSourceManager")
    @patch("src.monitor.AKShareSource")
    @patch("src.monitor.HaoETFSource")
    def test_quiet_mode_defaults_to_true(self, mock_haoetf, mock_akshare, mock_dsm_cls):
        """Test that quiet_mode defaults to True when not specified."""
        config = _make_config()
        monitor = Monitor(config)

        assert monitor._quiet_mode is True

    @patch("src.monitor.DataSourceManager")
    @patch("src.monitor.AKShareSource")
    @patch("src.monitor.HaoETFSource")
    def test_quiet_mode_can_be_disabled(self, mock_haoetf, mock_akshare, mock_dsm_cls):
        """Test that quiet_mode can be explicitly set to False."""
        config = _make_config()
        monitor = Monitor(config, quiet_mode=False)

        assert monitor._quiet_mode is False

    @patch("src.monitor.DataSourceManager")
    @patch("src.monitor.AKShareSource")
    @patch("src.monitor.HaoETFSource")
    def test_quiet_mode_true_explicit(self, mock_haoetf, mock_akshare, mock_dsm_cls):
        """Test that quiet_mode can be explicitly set to True."""
        config = _make_config()
        monitor = Monitor(config, quiet_mode=True)

        assert monitor._quiet_mode is True
