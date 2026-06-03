"""Unit tests for HaoETFSource."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from src.exceptions import DataFetchError
from src.haoetf_source import HaoETFSource
from src.models import ETFData


@pytest.fixture
def source() -> HaoETFSource:
    return HaoETFSource()


SAMPLE_HTML = """
<html>
<body>
<div class="etf-info">
    <span>当前价：1.234</span>
    <span>IOPV：1.200</span>
    <span>更新时间：2024-01-15 09:30:01</span>
</div>
</body>
</html>
"""

SAMPLE_HTML_ALT_FORMAT = """
<html>
<body>
<div>
    <span class="price">1.500</span>
    <span>估算净值：1.450</span>
    <span>2024/03/20 14:30</span>
</div>
</body>
</html>
"""


class TestHaoETFSourceFetch:
    """Tests for the fetch method."""

    @patch("src.haoetf_source.requests.get")
    def test_fetch_success(self, mock_get: MagicMock, source: HaoETFSource) -> None:
        """Test successful data fetch and parsing."""
        mock_response = MagicMock()
        mock_response.text = SAMPLE_HTML
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = source.fetch("513500")

        assert isinstance(result, ETFData)
        assert result.code == "513500"
        assert result.price == 1.234
        assert result.iopv == 1.200
        assert result.source == "HaoETF"
        assert result.update_time == datetime(2024, 1, 15, 9, 30, 1)
        mock_get.assert_called_once()

    @patch("src.haoetf_source.requests.get")
    def test_fetch_alt_format(self, mock_get: MagicMock, source: HaoETFSource) -> None:
        """Test parsing with alternative HTML format."""
        mock_response = MagicMock()
        mock_response.text = SAMPLE_HTML_ALT_FORMAT
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = source.fetch("159501")

        assert result.code == "159501"
        assert result.price == 1.500
        assert result.iopv == 1.450
        assert result.source == "HaoETF"
        assert result.update_time == datetime(2024, 3, 20, 14, 30)

    @patch("src.haoetf_source.requests.get")
    def test_fetch_timeout_raises_data_fetch_error(
        self, mock_get: MagicMock, source: HaoETFSource
    ) -> None:
        """Test that timeout raises DataFetchError."""
        import requests

        mock_get.side_effect = requests.Timeout("Connection timed out")

        with pytest.raises(DataFetchError) as exc_info:
            source.fetch("513500")

        assert exc_info.value.source == "HaoETF"
        assert exc_info.value.code == "513500"
        assert "超时" in exc_info.value.reason

    @patch("src.haoetf_source.requests.get")
    def test_fetch_connection_error_raises_data_fetch_error(
        self, mock_get: MagicMock, source: HaoETFSource
    ) -> None:
        """Test that connection errors raise DataFetchError."""
        import requests

        mock_get.side_effect = requests.ConnectionError("Failed to connect")

        with pytest.raises(DataFetchError) as exc_info:
            source.fetch("513500")

        assert exc_info.value.source == "HaoETF"
        assert exc_info.value.code == "513500"

    @patch("src.haoetf_source.requests.get")
    def test_fetch_http_error_raises_data_fetch_error(
        self, mock_get: MagicMock, source: HaoETFSource
    ) -> None:
        """Test that HTTP errors (4xx, 5xx) raise DataFetchError."""
        import requests

        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.HTTPError("404 Not Found")
        mock_get.return_value = mock_response

        with pytest.raises(DataFetchError) as exc_info:
            source.fetch("999999")

        assert exc_info.value.source == "HaoETF"
        assert exc_info.value.code == "999999"

    @patch("src.haoetf_source.requests.get")
    def test_fetch_no_price_raises_data_fetch_error(
        self, mock_get: MagicMock, source: HaoETFSource
    ) -> None:
        """Test that missing price data raises DataFetchError."""
        mock_response = MagicMock()
        mock_response.text = "<html><body>No data here</body></html>"
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        with pytest.raises(DataFetchError) as exc_info:
            source.fetch("513500")

        assert "价格" in exc_info.value.reason or "解析" in exc_info.value.reason

    @patch("src.haoetf_source.requests.get")
    def test_fetch_no_iopv_raises_data_fetch_error(
        self, mock_get: MagicMock, source: HaoETFSource
    ) -> None:
        """Test that missing IOPV data raises DataFetchError."""
        mock_response = MagicMock()
        mock_response.text = "<html><body>当前价：1.234</body></html>"
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        with pytest.raises(DataFetchError) as exc_info:
            source.fetch("513500")

        assert "IOPV" in exc_info.value.reason or "解析" in exc_info.value.reason

    @patch("src.haoetf_source.requests.get")
    def test_fetch_uses_correct_url(self, mock_get: MagicMock, source: HaoETFSource) -> None:
        """Test that the correct URL is constructed for the given code."""
        mock_response = MagicMock()
        mock_response.text = SAMPLE_HTML
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        source.fetch("513500")

        call_args = mock_get.call_args
        assert call_args[0][0] == "https://www.haoetf.com/etfdetail/513500.html"
        assert call_args[1]["timeout"] == 10

    @patch("src.haoetf_source.requests.get")
    def test_fetch_fallback_time_when_no_timestamp(
        self, mock_get: MagicMock, source: HaoETFSource
    ) -> None:
        """Test that current time is used when no timestamp in HTML."""
        html_no_time = """
        <html><body>
            <span>当前价：1.234</span>
            <span>IOPV：1.200</span>
        </body></html>
        """
        mock_response = MagicMock()
        mock_response.text = html_no_time
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        before = datetime.now()
        result = source.fetch("513500")
        after = datetime.now()

        assert before <= result.update_time <= after
