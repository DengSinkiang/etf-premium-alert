"""Unit tests for the Formatter module."""

from datetime import datetime

from src.formatter import format_plain_text, format_telegram_markdown
from src.models import MonitorResult


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
