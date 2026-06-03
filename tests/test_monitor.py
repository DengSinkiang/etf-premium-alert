"""Unit tests for the Monitor orchestrator."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from src.models import (
    AppConfig,
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
        mock_dsm.get_etf_data.return_value = _make_etf_data()
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
        mock_dsm.get_etf_data.return_value = None
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
            None,
            _make_etf_data(code="159501"),
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
        mock_dsm.get_etf_data.return_value = ETFData(
            code="513500",
            price=1.5,
            iopv=0.0,
            update_time=datetime(2024, 1, 15, 9, 30, 0),
            source="AKShare",
        )
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
        """Test that Telegram notification is sent when enabled."""
        config = _make_config(telegram_enabled=True)
        monitor = Monitor(config)

        mock_dsm = MagicMock()
        mock_dsm.get_etf_data.return_value = _make_etf_data()
        monitor._data_source_manager = mock_dsm

        mock_notifier = MagicMock()
        mock_notifier.send.return_value = True
        monitor._notifier = mock_notifier

        results = monitor.run()

        mock_notifier.send.assert_called_once()
        # Verify the message was formatted (contains ETF info)
        sent_message = mock_notifier.send.call_args[0][0]
        assert "513500" in sent_message

    @patch("src.monitor.DataSourceManager")
    @patch("src.monitor.AKShareSource")
    @patch("src.monitor.HaoETFSource")
    def test_telegram_not_sent_when_disabled(self, mock_haoetf, mock_akshare, mock_dsm_cls, capsys):
        """Test that Telegram notification is not sent when disabled."""
        config = _make_config(telegram_enabled=False)
        monitor = Monitor(config)

        mock_dsm = MagicMock()
        mock_dsm.get_etf_data.return_value = _make_etf_data()
        monitor._data_source_manager = mock_dsm

        mock_notifier = MagicMock()
        monitor._notifier = mock_notifier

        results = monitor.run()

        mock_notifier.send.assert_not_called()

    @patch("src.monitor.DataSourceManager")
    @patch("src.monitor.AKShareSource")
    @patch("src.monitor.HaoETFSource")
    def test_error_etf_included_in_telegram_notification(self, mock_haoetf, mock_akshare, mock_dsm_cls, capsys):
        """Test that error info is included in Telegram notification."""
        config = _make_config(telegram_enabled=True)
        monitor = Monitor(config)

        mock_dsm = MagicMock()
        mock_dsm.get_etf_data.return_value = None
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
        mock_dsm.get_etf_data.return_value = _make_etf_data()
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
