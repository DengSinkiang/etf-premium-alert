"""Tests for the --summary CLI flag in src/main.py."""

from unittest.mock import MagicMock, patch
from datetime import datetime

import pytest

from src.main import parse_args, _run_summary, main
from src.models import (
    AppConfig,
    DailySummaryReport,
    ETFConfig,
    ETFDailySummary,
    TelegramConfig,
)


@pytest.fixture
def sample_config():
    """Create a sample AppConfig for testing."""
    return AppConfig(
        etfs=[
            ETFConfig(
                code="513500",
                name="博时标普500ETF",
                target_amount=50000.0,
                bought_amount=10000.0,
                premium_rules=[],
                sell_threshold=8.0,
                discount_threshold=1.0,
            )
        ],
        telegram=TelegramConfig(enabled=False, bot_token=None, chat_id=None),
        alert_threshold=3.0,
        data_dir="data",
        summary_time="15:30",
    )


@pytest.fixture
def telegram_config():
    """Create a config with Telegram enabled."""
    return AppConfig(
        etfs=[
            ETFConfig(
                code="513500",
                name="博时标普500ETF",
                target_amount=50000.0,
                bought_amount=10000.0,
                premium_rules=[],
            )
        ],
        telegram=TelegramConfig(enabled=True, bot_token="token123", chat_id="chat123"),
        alert_threshold=3.0,
    )


@pytest.fixture
def sample_report():
    """Create a sample DailySummaryReport for testing."""
    return DailySummaryReport(
        date="2024-01-15",
        summaries=[
            ETFDailySummary(
                code="513500",
                name="博时标普500ETF",
                max_premium=2.50,
                min_premium=-0.30,
                close_premium=1.20,
                buy_triggered=True,
                sell_triggered=False,
                status="normal",
            )
        ],
    )


class TestParseArgs:
    """Tests for parse_args with --summary flag."""

    def test_summary_flag_default_false(self):
        """--summary defaults to False when not specified."""
        args = parse_args([])
        assert args.summary is False

    def test_summary_flag_set(self):
        """--summary is True when specified."""
        args = parse_args(["--summary"])
        assert args.summary is True

    def test_summary_with_config(self):
        """--summary can be combined with --config."""
        args = parse_args(["--summary", "--config", "custom.yaml"])
        assert args.summary is True
        assert args.config == "custom.yaml"

    def test_force_flag_default_false(self):
        """--force defaults to False when not specified."""
        args = parse_args([])
        assert args.force is False

    def test_force_flag_set(self):
        """--force is True when specified."""
        args = parse_args(["--force"])
        assert args.force is True


class TestRunSummary:
    """Tests for the _run_summary function."""

    @patch("src.premium_store.PremiumStore")
    def test_run_summary_generates_and_prints(
        self, mock_store_cls, sample_config, sample_report, capsys
    ):
        """_run_summary generates report and prints plain text to stdout."""
        mock_reporter = MagicMock()
        mock_reporter.generate.return_value = sample_report

        with patch("src.daily_summary.DailySummaryReporter", return_value=mock_reporter):
            result = _run_summary(sample_config)

        assert result == 0

        # Check stdout contains summary output
        captured = capsys.readouterr()
        assert "513500" in captured.out
        assert "博时标普500ETF" in captured.out
        assert "每日摘要报告" in captured.out

    @patch("src.premium_store.PremiumStore")
    def test_run_summary_sends_telegram_when_enabled(
        self, mock_store_cls, telegram_config, sample_report, capsys
    ):
        """_run_summary pushes Telegram message when telegram is enabled."""
        mock_reporter = MagicMock()
        mock_reporter.generate.return_value = sample_report

        mock_notifier = MagicMock()
        mock_notifier.send.return_value = True

        with patch("src.daily_summary.DailySummaryReporter", return_value=mock_reporter), \
             patch("src.notifier.TelegramNotifier", return_value=mock_notifier) as mock_notifier_cls:
            result = _run_summary(telegram_config)

        assert result == 0
        mock_notifier_cls.assert_called_once_with(telegram_config.telegram)
        mock_notifier.send.assert_called_once()

    @patch("src.premium_store.PremiumStore")
    def test_run_summary_skips_telegram_when_disabled(
        self, mock_store_cls, sample_config, sample_report, capsys
    ):
        """_run_summary does not push Telegram when telegram is disabled."""
        mock_reporter = MagicMock()
        mock_reporter.generate.return_value = sample_report

        mock_notifier_cls = MagicMock()

        with patch("src.daily_summary.DailySummaryReporter", return_value=mock_reporter), \
             patch("src.notifier.TelegramNotifier", mock_notifier_cls):
            result = _run_summary(sample_config)

        assert result == 0
        # Notifier should not be instantiated when telegram is disabled
        mock_notifier_cls.assert_not_called()

    @patch("src.premium_store.PremiumStore")
    def test_run_summary_logs_error_on_telegram_failure(
        self, mock_store_cls, telegram_config, sample_report, capsys
    ):
        """_run_summary logs error when Telegram push fails, does not retry."""
        mock_reporter = MagicMock()
        mock_reporter.generate.return_value = sample_report

        mock_notifier = MagicMock()
        mock_notifier.send.return_value = False  # Simulate failure

        with patch("src.daily_summary.DailySummaryReporter", return_value=mock_reporter), \
             patch("src.notifier.TelegramNotifier", return_value=mock_notifier):
            result = _run_summary(telegram_config)

        # Should still return 0 (no retry, just log error)
        assert result == 0
        # send is called exactly once (no retry)
        mock_notifier.send.assert_called_once()


class TestMainWithSummary:
    """Tests for main() function with --summary flag."""

    @patch("src.main._run_summary")
    @patch("src.main.load_config")
    @patch("src.main.setup_logging")
    def test_main_calls_run_summary(self, mock_logging, mock_load, mock_run_summary, sample_config):
        """main() calls _run_summary when --summary is passed."""
        mock_load.return_value = sample_config
        mock_run_summary.return_value = 0

        result = main(["--summary"])

        assert result == 0
        mock_run_summary.assert_called_once_with(sample_config)

    @patch("src.main.TradingCalendar")
    @patch("src.main.Monitor")
    @patch("src.main.load_config")
    @patch("src.main.setup_logging")
    def test_main_without_summary_runs_monitor(self, mock_logging, mock_load, mock_monitor_cls, mock_calendar_cls, sample_config):
        """main() runs Monitor when --summary is not passed."""
        mock_load.return_value = sample_config
        mock_monitor = MagicMock()
        mock_monitor_cls.return_value = mock_monitor
        mock_calendar = MagicMock()
        mock_calendar.is_trading_day.return_value = True
        mock_calendar_cls.return_value = mock_calendar

        result = main([])

        assert result == 0
        mock_monitor_cls.assert_called_once_with(sample_config, quiet_mode=True)
        mock_monitor.run.assert_called_once()


class TestNoQuietFlag:
    """Tests for --no-quiet flag."""

    def test_no_quiet_flag_default_false(self):
        """--no-quiet defaults to False when not specified."""
        args = parse_args([])
        assert args.no_quiet is False

    def test_no_quiet_flag_set(self):
        """--no-quiet is True when specified."""
        args = parse_args(["--no-quiet"])
        assert args.no_quiet is True

    def test_no_quiet_with_force(self):
        """--no-quiet can be combined with --force."""
        args = parse_args(["--no-quiet", "--force"])
        assert args.no_quiet is True
        assert args.force is True

    @patch("src.main.TradingCalendar")
    @patch("src.main.Monitor")
    @patch("src.main.load_config")
    @patch("src.main.setup_logging")
    def test_no_quiet_passes_quiet_mode_false(
        self, mock_logging, mock_load, mock_monitor_cls, mock_calendar_cls, sample_config
    ):
        """main(["--no-quiet"]) passes quiet_mode=False to Monitor."""
        mock_load.return_value = sample_config
        mock_monitor = MagicMock()
        mock_monitor_cls.return_value = mock_monitor
        mock_calendar = MagicMock()
        mock_calendar.is_trading_day.return_value = True
        mock_calendar_cls.return_value = mock_calendar

        result = main(["--no-quiet"])

        assert result == 0
        mock_monitor_cls.assert_called_once_with(sample_config, quiet_mode=False)


class TestTradingCalendarIntegration:
    """Tests for TradingCalendar integration in main()."""

    @patch("src.main.TradingCalendar")
    @patch("src.main.Monitor")
    @patch("src.main.load_config")
    @patch("src.main.setup_logging")
    def test_trading_calendar_called_in_main(
        self, mock_logging, mock_load, mock_monitor_cls, mock_calendar_cls, sample_config
    ):
        """main([]) calls TradingCalendar.is_trading_day()."""
        mock_load.return_value = sample_config
        mock_monitor = MagicMock()
        mock_monitor_cls.return_value = mock_monitor
        mock_calendar = MagicMock()
        mock_calendar.is_trading_day.return_value = True
        mock_calendar_cls.return_value = mock_calendar

        main([])

        mock_calendar_cls.assert_called_once()
        mock_calendar.is_trading_day.assert_called_once()

    @patch("src.main.TradingCalendar")
    @patch("src.main.Monitor")
    @patch("src.main.load_config")
    @patch("src.main.setup_logging")
    def test_non_trading_day_skips_monitor(
        self, mock_logging, mock_load, mock_monitor_cls, mock_calendar_cls, sample_config
    ):
        """main([]) skips Monitor when is_trading_day() returns False."""
        mock_load.return_value = sample_config
        mock_calendar = MagicMock()
        mock_calendar.is_trading_day.return_value = False
        mock_calendar_cls.return_value = mock_calendar

        result = main([])

        assert result == 0
        mock_monitor_cls.assert_not_called()

    @patch("src.main.TradingCalendar")
    @patch("src.main.Monitor")
    @patch("src.main.load_config")
    @patch("src.main.setup_logging")
    def test_calendar_exception_proceeds(
        self, mock_logging, mock_load, mock_monitor_cls, mock_calendar_cls, sample_config
    ):
        """main([]) proceeds with Monitor when is_trading_day() raises."""
        mock_load.return_value = sample_config
        mock_monitor = MagicMock()
        mock_monitor_cls.return_value = mock_monitor
        mock_calendar = MagicMock()
        mock_calendar.is_trading_day.side_effect = RuntimeError("calendar error")
        mock_calendar_cls.return_value = mock_calendar

        result = main([])

        assert result == 0
        mock_monitor_cls.assert_called_once_with(sample_config, quiet_mode=True)
        mock_monitor.run.assert_called_once()

    @patch("src.main.TradingCalendar")
    @patch("src.main.Monitor")
    @patch("src.main.load_config")
    @patch("src.main.setup_logging")
    def test_force_flag_skips_calendar(
        self, mock_logging, mock_load, mock_monitor_cls, mock_calendar_cls, sample_config
    ):
        """main(["--force"]) does not call TradingCalendar."""
        mock_load.return_value = sample_config
        mock_monitor = MagicMock()
        mock_monitor_cls.return_value = mock_monitor

        result = main(["--force"])

        assert result == 0
        mock_calendar_cls.assert_not_called()
        mock_monitor_cls.assert_called_once_with(sample_config, quiet_mode=True)
        mock_monitor.run.assert_called_once()

    @patch("src.main._run_summary")
    @patch("src.main.TradingCalendar")
    @patch("src.main.load_config")
    @patch("src.main.setup_logging")
    def test_summary_flag_skips_calendar(
        self, mock_logging, mock_load, mock_calendar_cls, mock_run_summary, sample_config
    ):
        """main(["--summary"]) does not call TradingCalendar."""
        mock_load.return_value = sample_config
        mock_run_summary.return_value = 0

        result = main(["--summary"])

        assert result == 0
        mock_calendar_cls.assert_not_called()
        mock_run_summary.assert_called_once_with(sample_config)
