"""Unit tests for the Formatter module."""

from datetime import datetime

from src.formatter import (
    format_plain_text,
    format_telegram_markdown,
    format_discount_alert_plain,
    format_discount_alert_telegram,
    format_volume_info_plain,
    format_daily_summary_plain,
    format_daily_summary_telegram,
    format_trend_indicator,
)
from src.models import MonitorResult, DiscountAlertResult, ETFDailySummary, DailySummaryReport, TrendInfo


def _make_normal_result() -> MonitorResult:
    """Create a normal MonitorResult for testing."""
    return MonitorResult(
        code="513500",
        name="博时标普500ETF",
        price=1.234,
        iopv=1.200,
        premium_rate=2.83,
        target_amount=100000.0,
        bought_amount=30000.0,
        remaining_target=70000.0,
        suggested_buy_min=21000,
        suggested_buy_max=35000,
        suggestion="可以分批买",
        source="AKShare",
        update_time=datetime(2024, 1, 15, 9, 30, 0),
        error=None,
    )


def _make_error_result() -> MonitorResult:
    """Create an error MonitorResult for testing."""
    return MonitorResult(
        code="159501",
        name="嘉实纳斯达克100ETF",
        price=None,
        iopv=None,
        premium_rate=None,
        target_amount=80000.0,
        bought_amount=20000.0,
        remaining_target=60000.0,
        suggested_buy_min=None,
        suggested_buy_max=None,
        suggestion=None,
        source=None,
        update_time=None,
        error="数据源获取失败: AKShare 和 HaoETF 均超时",
    )


class TestFormatPlainText:
    """Tests for format_plain_text."""

    def test_normal_result_contains_all_fields(self):
        result = _make_normal_result()
        output = format_plain_text([result])

        assert "513500" in output
        assert "博时标普500ETF" in output
        assert "1.234" in output
        assert "1.2" in output
        assert "2.83" in output
        assert "100000" in output
        assert "30000" in output
        assert "70000" in output
        assert "21000" in output
        assert "35000" in output
        assert "可以分批买" in output
        assert "AKShare" in output
        assert "2024-01-15 09:30:00" in output

    def test_error_result_shows_error_message(self):
        result = _make_error_result()
        output = format_plain_text([result])

        assert "159501" in output
        assert "嘉实纳斯达克100ETF" in output
        assert "数据源获取失败" in output
        assert "AKShare 和 HaoETF 均超时" in output

    def test_multiple_results_have_dividers(self):
        results = [_make_normal_result(), _make_error_result()]
        output = format_plain_text(results)

        assert "---" in output
        assert "513500" in output
        assert "159501" in output

    def test_header_contains_timestamp(self):
        output = format_plain_text([_make_normal_result()])
        assert "QDII ETF 溢价率监控" in output

    def test_empty_results(self):
        output = format_plain_text([])
        assert "QDII ETF 溢价率监控" in output


class TestFormatTelegramMarkdown:
    """Tests for format_telegram_markdown."""

    def test_normal_result_contains_all_fields(self):
        result = _make_normal_result()
        output = format_telegram_markdown([result])

        assert "513500" in output
        assert "博时标普500ETF" in output
        assert "1.234" in output or "1\\.234" in output
        assert "2.83" in output or "2\\.83" in output
        assert "100000" in output
        assert "30000" in output
        assert "70000" in output
        assert "21000" in output
        assert "35000" in output
        assert "可以分批买" in output
        assert "AKShare" in output
        assert "2024" in output
        assert "09:30:00" in output or "09\\:30\\:00" in output

    def test_uses_markdown_bold(self):
        result = _make_normal_result()
        output = format_telegram_markdown([result])
        # Header should be bold
        assert "*QDII ETF 溢价率监控*" in output

    def test_uses_monospace(self):
        result = _make_normal_result()
        output = format_telegram_markdown([result])
        # Field labels should use monospace
        assert "`当前价格:`" in output
        assert "`估算净值:`" in output

    def test_error_result_shows_error_message(self):
        result = _make_error_result()
        output = format_telegram_markdown([result])

        assert "159501" in output
        assert "嘉实纳斯达克100ETF" in output
        assert "数据源获取失败" in output

    def test_multiple_results_have_dividers(self):
        results = [_make_normal_result(), _make_error_result()]
        output = format_telegram_markdown(results)

        assert "\\-\\-\\-" in output

    def test_header_is_bold(self):
        output = format_telegram_markdown([_make_normal_result()])
        assert output.startswith("*QDII ETF 溢价率监控*")


class TestFormatDiscountAlertPlain:
    """Tests for format_discount_alert_plain (Task 6.1)."""

    def test_contains_all_fields(self):
        alert = DiscountAlertResult(
            code="513500",
            name="博时标普500ETF",
            discount_rate=1.50,
            price=1.180,
            iopv=1.198,
        )
        output = format_discount_alert_plain(alert)

        assert "513500" in output
        assert "博时标普500ETF" in output
        assert "1.50%" in output
        assert "1.18" in output
        assert "1.198" in output

    def test_discount_rate_two_decimal_places(self):
        alert = DiscountAlertResult(
            code="159612",
            name="纳指ETF",
            discount_rate=2.3456,
            price=1.000,
            iopv=1.024,
        )
        output = format_discount_alert_plain(alert)
        assert "2.35%" in output  # rounded to 2 decimal places

    def test_header_contains_discount_hint(self):
        alert = DiscountAlertResult(
            code="513500",
            name="博时标普500ETF",
            discount_rate=1.50,
            price=1.180,
            iopv=1.198,
        )
        output = format_discount_alert_plain(alert)
        assert "折价买入提醒" in output


class TestFormatDiscountAlertTelegram:
    """Tests for format_discount_alert_telegram (Task 6.1)."""

    def test_contains_all_fields(self):
        alert = DiscountAlertResult(
            code="513500",
            name="博时标普500ETF",
            discount_rate=1.50,
            price=1.180,
            iopv=1.198,
        )
        output = format_discount_alert_telegram(alert)

        assert "513500" in output
        assert "博时标普500ETF" in output
        assert "1.50" in output or "1\\.50" in output
        assert "1.18" in output or "1\\.18" in output
        assert "1.198" in output or "1\\.198" in output

    def test_uses_markdown_bold(self):
        alert = DiscountAlertResult(
            code="513500",
            name="博时标普500ETF",
            discount_rate=1.50,
            price=1.180,
            iopv=1.198,
        )
        output = format_discount_alert_telegram(alert)
        assert "*折价买入提醒*" in output

    def test_escapes_special_chars(self):
        alert = DiscountAlertResult(
            code="513500",
            name="博时标普500ETF",
            discount_rate=1.50,
            price=1.180,
            iopv=1.198,
        )
        output = format_discount_alert_telegram(alert)
        # Dot in numbers should be escaped
        assert "1\\.50" in output


class TestFormatVolumeInfoPlain:
    """Tests for format_volume_info_plain (Task 6.3)."""

    def test_normal_values(self):
        output = format_volume_info_plain(1234500.0, 1.23)
        assert "123.45 万手" in output
        assert "1.23%" in output

    def test_volume_none(self):
        output = format_volume_info_plain(None, 1.23)
        assert "N/A" in output
        assert "1.23%" in output

    def test_turnover_rate_none(self):
        output = format_volume_info_plain(1234500.0, None)
        assert "123.45 万手" in output
        assert "N/A" in output

    def test_both_none(self):
        output = format_volume_info_plain(None, None)
        # Both should show N/A
        assert output.count("N/A") == 2

    def test_small_volume(self):
        output = format_volume_info_plain(100.0, 0.01)
        assert "0.01 万手" in output
        assert "0.01%" in output

    def test_large_volume(self):
        output = format_volume_info_plain(50000000.0, 5.67)
        assert "5000.00 万手" in output
        assert "5.67%" in output


class TestVolumeIntegrationPlainText:
    """Tests for volume display integration in format_plain_text."""

    def test_volume_shown_when_present(self):
        result = MonitorResult(
            code="513500",
            name="博时标普500ETF",
            price=1.234,
            iopv=1.200,
            premium_rate=5.0,
            target_amount=100000.0,
            bought_amount=30000.0,
            remaining_target=70000.0,
            suggested_buy_min=21000,
            suggested_buy_max=35000,
            suggestion="可以分批买",
            source="AKShare",
            update_time=datetime(2024, 1, 15, 9, 30, 0),
            error=None,
            volume=1234500.0,
            turnover_rate=1.23,
        )
        output = format_plain_text([result])
        assert "123.45 万手" in output
        assert "1.23%" in output

    def test_volume_not_shown_when_none(self):
        result = MonitorResult(
            code="513500",
            name="博时标普500ETF",
            price=1.234,
            iopv=1.200,
            premium_rate=2.0,
            target_amount=100000.0,
            bought_amount=30000.0,
            remaining_target=70000.0,
            suggested_buy_min=21000,
            suggested_buy_max=35000,
            suggestion="可以分批买",
            source="AKShare",
            update_time=datetime(2024, 1, 15, 9, 30, 0),
            error=None,
            volume=None,
            turnover_rate=None,
        )
        output = format_plain_text([result])
        assert "成交量" not in output
        assert "换手率" not in output


class TestVolumeIntegrationTelegram:
    """Tests for volume display integration in format_telegram_markdown."""

    def test_volume_shown_when_present(self):
        result = MonitorResult(
            code="513500",
            name="博时标普500ETF",
            price=1.234,
            iopv=1.200,
            premium_rate=5.0,
            target_amount=100000.0,
            bought_amount=30000.0,
            remaining_target=70000.0,
            suggested_buy_min=21000,
            suggested_buy_max=35000,
            suggestion="可以分批买",
            source="AKShare",
            update_time=datetime(2024, 1, 15, 9, 30, 0),
            error=None,
            volume=1234500.0,
            turnover_rate=1.23,
        )
        output = format_telegram_markdown([result])
        assert "成交量" in output
        assert "换手率" in output

    def test_volume_not_shown_when_none(self):
        result = MonitorResult(
            code="513500",
            name="博时标普500ETF",
            price=1.234,
            iopv=1.200,
            premium_rate=2.0,
            target_amount=100000.0,
            bought_amount=30000.0,
            remaining_target=70000.0,
            suggested_buy_min=21000,
            suggested_buy_max=35000,
            suggestion="可以分批买",
            source="AKShare",
            update_time=datetime(2024, 1, 15, 9, 30, 0),
            error=None,
            volume=None,
            turnover_rate=None,
        )
        output = format_telegram_markdown([result])
        assert "成交量" not in output
        assert "换手率" not in output


class TestFormatDailySummaryPlain:
    """Tests for format_daily_summary_plain (Task 6.5)."""

    def _make_normal_summary(self) -> ETFDailySummary:
        return ETFDailySummary(
            code="513500",
            name="博时标普500ETF",
            max_premium=3.50,
            min_premium=-0.20,
            close_premium=1.80,
            buy_triggered=True,
            sell_triggered=False,
            status="normal",
        )

    def _make_no_data_summary(self) -> ETFDailySummary:
        return ETFDailySummary(
            code="159612",
            name="纳指ETF",
            max_premium=None,
            min_premium=None,
            close_premium=None,
            buy_triggered=False,
            sell_triggered=False,
            status="no_data",
        )

    def _make_read_error_summary(self) -> ETFDailySummary:
        return ETFDailySummary(
            code="159501",
            name="嘉实纳斯达克100ETF",
            max_premium=None,
            min_premium=None,
            close_premium=None,
            buy_triggered=False,
            sell_triggered=False,
            status="read_error",
        )

    def test_header_contains_date(self):
        report = DailySummaryReport(date="2024-01-15", summaries=[self._make_normal_summary()])
        output = format_daily_summary_plain(report)
        assert "每日摘要报告" in output
        assert "2024-01-15" in output

    def test_normal_summary_contains_all_fields(self):
        report = DailySummaryReport(date="2024-01-15", summaries=[self._make_normal_summary()])
        output = format_daily_summary_plain(report)

        assert "513500" in output
        assert "博时标普500ETF" in output
        assert "3.50%" in output
        assert "-0.20%" in output
        assert "1.80%" in output
        assert "✅" in output  # buy_triggered
        assert "❌" in output  # sell_triggered

    def test_normal_summary_premium_two_decimal(self):
        summary = ETFDailySummary(
            code="513500",
            name="Test",
            max_premium=3.456,
            min_premium=-1.789,
            close_premium=2.1,
            buy_triggered=False,
            sell_triggered=False,
            status="normal",
        )
        report = DailySummaryReport(date="2024-01-15", summaries=[summary])
        output = format_daily_summary_plain(report)

        assert "3.46%" in output  # rounded
        assert "-1.79%" in output  # rounded
        assert "2.10%" in output  # padded

    def test_no_data_summary(self):
        report = DailySummaryReport(date="2024-01-15", summaries=[self._make_no_data_summary()])
        output = format_daily_summary_plain(report)

        assert "159612" in output
        assert "纳指ETF" in output
        assert "当日无数据" in output

    def test_read_error_summary(self):
        report = DailySummaryReport(date="2024-01-15", summaries=[self._make_read_error_summary()])
        output = format_daily_summary_plain(report)

        assert "159501" in output
        assert "嘉实纳斯达克100ETF" in output
        assert "数据读取失败" in output

    def test_multiple_summaries_have_dividers(self):
        report = DailySummaryReport(
            date="2024-01-15",
            summaries=[self._make_normal_summary(), self._make_no_data_summary()],
        )
        output = format_daily_summary_plain(report)
        assert "---" in output

    def test_buy_and_sell_triggered(self):
        summary = ETFDailySummary(
            code="513500",
            name="Test",
            max_premium=10.0,
            min_premium=-2.0,
            close_premium=5.0,
            buy_triggered=True,
            sell_triggered=True,
            status="normal",
        )
        report = DailySummaryReport(date="2024-01-15", summaries=[summary])
        output = format_daily_summary_plain(report)

        # Both should show ✅
        assert output.count("✅") == 2


class TestFormatDailySummaryTelegram:
    """Tests for format_daily_summary_telegram (Task 6.5)."""

    def _make_normal_summary(self) -> ETFDailySummary:
        return ETFDailySummary(
            code="513500",
            name="博时标普500ETF",
            max_premium=3.50,
            min_premium=-0.20,
            close_premium=1.80,
            buy_triggered=True,
            sell_triggered=False,
            status="normal",
        )

    def _make_no_data_summary(self) -> ETFDailySummary:
        return ETFDailySummary(
            code="159612",
            name="纳指ETF",
            max_premium=None,
            min_premium=None,
            close_premium=None,
            buy_triggered=False,
            sell_triggered=False,
            status="no_data",
        )

    def _make_read_error_summary(self) -> ETFDailySummary:
        return ETFDailySummary(
            code="159501",
            name="嘉实纳斯达克100ETF",
            max_premium=None,
            min_premium=None,
            close_premium=None,
            buy_triggered=False,
            sell_triggered=False,
            status="read_error",
        )

    def test_header_is_bold(self):
        report = DailySummaryReport(date="2024-01-15", summaries=[self._make_normal_summary()])
        output = format_daily_summary_telegram(report)
        assert "*每日摘要报告*" in output

    def test_header_contains_date(self):
        report = DailySummaryReport(date="2024-01-15", summaries=[self._make_normal_summary()])
        output = format_daily_summary_telegram(report)
        assert "2024" in output
        assert "01" in output
        assert "15" in output

    def test_normal_summary_contains_all_fields(self):
        report = DailySummaryReport(date="2024-01-15", summaries=[self._make_normal_summary()])
        output = format_daily_summary_telegram(report)

        assert "513500" in output
        assert "博时标普500ETF" in output
        assert "3\\.50" in output  # escaped dot
        assert "0\\.20" in output  # escaped dot
        assert "1\\.80" in output  # escaped dot
        assert "✅" in output
        assert "❌" in output

    def test_normal_summary_uses_monospace_labels(self):
        report = DailySummaryReport(date="2024-01-15", summaries=[self._make_normal_summary()])
        output = format_daily_summary_telegram(report)

        assert "`最高溢价率:`" in output
        assert "`最低溢价率:`" in output
        assert "`收盘溢价率:`" in output
        assert "`买入触发:`" in output
        assert "`卖出触发:`" in output

    def test_no_data_summary(self):
        report = DailySummaryReport(date="2024-01-15", summaries=[self._make_no_data_summary()])
        output = format_daily_summary_telegram(report)

        assert "159612" in output
        assert "当日无数据" in output

    def test_read_error_summary(self):
        report = DailySummaryReport(date="2024-01-15", summaries=[self._make_read_error_summary()])
        output = format_daily_summary_telegram(report)

        assert "159501" in output
        assert "数据读取失败" in output

    def test_multiple_summaries_have_dividers(self):
        report = DailySummaryReport(
            date="2024-01-15",
            summaries=[self._make_normal_summary(), self._make_no_data_summary()],
        )
        output = format_daily_summary_telegram(report)
        assert "\\-\\-\\-" in output

    def test_escapes_special_chars_in_premium(self):
        summary = ETFDailySummary(
            code="513500",
            name="博时标普500ETF",
            max_premium=3.50,
            min_premium=-0.20,
            close_premium=1.80,
            buy_triggered=False,
            sell_triggered=False,
            status="normal",
        )
        report = DailySummaryReport(date="2024-01-15", summaries=[summary])
        output = format_daily_summary_telegram(report)
        # Dots and minus should be escaped in percentages
        assert "3\\.50" in output
        assert "\\-0\\.20" in output or "0\\.20" in output


class TestDailySummaryTrendPlain:
    """Tests for daily summary trend info in plain text (Task 7.2)."""

    def test_trend_shown_when_open_and_close_available(self):
        summary = ETFDailySummary(
            code="513500",
            name="博时标普500ETF",
            max_premium=3.50,
            min_premium=-0.20,
            close_premium=2.80,
            buy_triggered=False,
            sell_triggered=False,
            status="normal",
            open_premium=1.57,
            trend_path=None,
        )
        report = DailySummaryReport(date="2024-01-15", summaries=[summary])
        output = format_daily_summary_plain(report)
        assert "日内走势:" in output
        assert "↑" in output
        assert "+1.23%" in output

    def test_trend_down_arrow(self):
        summary = ETFDailySummary(
            code="513500",
            name="博时标普500ETF",
            max_premium=3.50,
            min_premium=-0.20,
            close_premium=1.00,
            buy_triggered=False,
            sell_triggered=False,
            status="normal",
            open_premium=1.58,
            trend_path=None,
        )
        report = DailySummaryReport(date="2024-01-15", summaries=[summary])
        output = format_daily_summary_plain(report)
        assert "↓" in output
        assert "-0.58%" in output

    def test_trend_right_arrow_when_equal(self):
        summary = ETFDailySummary(
            code="513500",
            name="博时标普500ETF",
            max_premium=3.50,
            min_premium=-0.20,
            close_premium=2.00,
            buy_triggered=False,
            sell_triggered=False,
            status="normal",
            open_premium=2.00,
            trend_path=None,
        )
        report = DailySummaryReport(date="2024-01-15", summaries=[summary])
        output = format_daily_summary_plain(report)
        assert "→" in output
        assert "+0.00%" in output

    def test_trend_not_shown_when_open_is_none(self):
        summary = ETFDailySummary(
            code="513500",
            name="博时标普500ETF",
            max_premium=3.50,
            min_premium=-0.20,
            close_premium=2.00,
            buy_triggered=False,
            sell_triggered=False,
            status="normal",
            open_premium=None,
            trend_path=None,
        )
        report = DailySummaryReport(date="2024-01-15", summaries=[summary])
        output = format_daily_summary_plain(report)
        assert "日内走势" not in output

    def test_trend_path_shown_when_available(self):
        summary = ETFDailySummary(
            code="513500",
            name="博时标普500ETF",
            max_premium=3.50,
            min_premium=-0.20,
            close_premium=2.00,
            buy_triggered=False,
            sell_triggered=False,
            status="normal",
            open_premium=1.00,
            trend_path="低→高→低",
        )
        report = DailySummaryReport(date="2024-01-15", summaries=[summary])
        output = format_daily_summary_plain(report)
        assert "走势路径:" in output
        assert "低→高→低" in output

    def test_trend_path_not_shown_when_none(self):
        summary = ETFDailySummary(
            code="513500",
            name="博时标普500ETF",
            max_premium=3.50,
            min_premium=-0.20,
            close_premium=2.00,
            buy_triggered=False,
            sell_triggered=False,
            status="normal",
            open_premium=1.00,
            trend_path=None,
        )
        report = DailySummaryReport(date="2024-01-15", summaries=[summary])
        output = format_daily_summary_plain(report)
        assert "走势路径" not in output

    def test_no_data_status_omits_trend(self):
        summary = ETFDailySummary(
            code="513500",
            name="博时标普500ETF",
            max_premium=None,
            min_premium=None,
            close_premium=None,
            buy_triggered=False,
            sell_triggered=False,
            status="no_data",
            open_premium=None,
            trend_path=None,
        )
        report = DailySummaryReport(date="2024-01-15", summaries=[summary])
        output = format_daily_summary_plain(report)
        assert "日内走势" not in output
        assert "走势路径" not in output


class TestDailySummaryTrendTelegram:
    """Tests for daily summary trend info in Telegram format (Task 7.2)."""

    def test_trend_shown_when_open_and_close_available(self):
        summary = ETFDailySummary(
            code="513500",
            name="博时标普500ETF",
            max_premium=3.50,
            min_premium=-0.20,
            close_premium=2.80,
            buy_triggered=False,
            sell_triggered=False,
            status="normal",
            open_premium=1.57,
            trend_path=None,
        )
        report = DailySummaryReport(date="2024-01-15", summaries=[summary])
        output = format_daily_summary_telegram(report)
        assert "`日内走势:`" in output
        assert "↑" in output
        # delta = 2.80 - 1.57 = 1.23
        assert "1\\.23" in output

    def test_trend_down_arrow_telegram(self):
        summary = ETFDailySummary(
            code="513500",
            name="博时标普500ETF",
            max_premium=3.50,
            min_premium=-0.20,
            close_premium=1.00,
            buy_triggered=False,
            sell_triggered=False,
            status="normal",
            open_premium=1.58,
            trend_path=None,
        )
        report = DailySummaryReport(date="2024-01-15", summaries=[summary])
        output = format_daily_summary_telegram(report)
        assert "↓" in output
        assert "0\\.58" in output

    def test_trend_path_shown_telegram(self):
        summary = ETFDailySummary(
            code="513500",
            name="博时标普500ETF",
            max_premium=3.50,
            min_premium=-0.20,
            close_premium=2.00,
            buy_triggered=False,
            sell_triggered=False,
            status="normal",
            open_premium=1.00,
            trend_path="低→高→低",
        )
        report = DailySummaryReport(date="2024-01-15", summaries=[summary])
        output = format_daily_summary_telegram(report)
        assert "`走势路径:`" in output
        assert "低→高→低" in output

    def test_trend_path_not_shown_when_none_telegram(self):
        summary = ETFDailySummary(
            code="513500",
            name="博时标普500ETF",
            max_premium=3.50,
            min_premium=-0.20,
            close_premium=2.00,
            buy_triggered=False,
            sell_triggered=False,
            status="normal",
            open_premium=1.00,
            trend_path=None,
        )
        report = DailySummaryReport(date="2024-01-15", summaries=[summary])
        output = format_daily_summary_telegram(report)
        assert "走势路径" not in output

    def test_trend_not_shown_when_open_is_none_telegram(self):
        summary = ETFDailySummary(
            code="513500",
            name="博时标普500ETF",
            max_premium=3.50,
            min_premium=-0.20,
            close_premium=2.00,
            buy_triggered=False,
            sell_triggered=False,
            status="normal",
            open_premium=None,
            trend_path=None,
        )
        report = DailySummaryReport(date="2024-01-15", summaries=[summary])
        output = format_daily_summary_telegram(report)
        assert "日内走势" not in output


class TestFormatTrendIndicator:
    """Tests for format_trend_indicator (Task 3.2)."""

    def test_none_returns_empty_string(self):
        assert format_trend_indicator(None) == ""

    def test_positive_delta_shows_up_arrow_with_plus(self):
        trend = TrendInfo(arrow="↑", delta=0.50, previous_rate=2.00)
        assert format_trend_indicator(trend) == "↑ +0.50%"

    def test_negative_delta_shows_down_arrow_with_minus(self):
        trend = TrendInfo(arrow="↓", delta=-0.30, previous_rate=2.00)
        assert format_trend_indicator(trend) == "↓ -0.30%"

    def test_zero_delta_shows_right_arrow_with_plus(self):
        trend = TrendInfo(arrow="→", delta=0.00, previous_rate=2.00)
        assert format_trend_indicator(trend) == "→ +0.00%"

    def test_exactly_two_decimal_places(self):
        trend = TrendInfo(arrow="↑", delta=1.0, previous_rate=1.00)
        assert format_trend_indicator(trend) == "↑ +1.00%"

    def test_large_positive_delta(self):
        trend = TrendInfo(arrow="↑", delta=5.67, previous_rate=0.00)
        assert format_trend_indicator(trend) == "↑ +5.67%"

    def test_large_negative_delta(self):
        trend = TrendInfo(arrow="↓", delta=-3.21, previous_rate=5.00)
        assert format_trend_indicator(trend) == "↓ -3.21%"

    def test_small_positive_near_threshold(self):
        trend = TrendInfo(arrow="↑", delta=0.01, previous_rate=1.00)
        assert format_trend_indicator(trend) == "↑ +0.01%"

    def test_small_negative_near_threshold(self):
        trend = TrendInfo(arrow="↓", delta=-0.01, previous_rate=1.00)
        assert format_trend_indicator(trend) == "↓ -0.01%"
