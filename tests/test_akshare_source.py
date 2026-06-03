"""Unit tests for AKShareSource."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.akshare_source import AKShareSource
from src.exceptions import DataFetchError
from src.models import ETFData


@pytest.fixture
def source() -> AKShareSource:
    return AKShareSource()


def _make_etf_dataframe(
    code: str = "513500",
    price: float = 2.611,
    iopv: float = 2.580,
    update_time: str = "2024-01-15 09:30:01",
) -> pd.DataFrame:
    """Helper to create a mock DataFrame matching fund_etf_spot_em output."""
    return pd.DataFrame(
        [
            {
                "代码": code,
                "名称": "标普500ETF博时",
                "最新价": price,
                "IOPV实时估值": iopv,
                "更新时间": pd.Timestamp(update_time),
                "数据日期": "2024-01-15",
            }
        ]
    )


class TestAKShareSourceFetch:
    """Tests for the AKShareSource.fetch method."""

    @patch("src.akshare_source.ak.fund_etf_spot_em")
    def test_fetch_success(self, mock_api: MagicMock, source: AKShareSource) -> None:
        """Test successful data fetch returns ETFData with correct values."""
        mock_api.return_value = _make_etf_dataframe(
            code="513500", price=2.611, iopv=2.580, update_time="2024-01-15 09:30:01"
        )

        result = source.fetch("513500")

        assert isinstance(result, ETFData)
        assert result.code == "513500"
        assert result.price == 2.611
        assert result.iopv == 2.580
        assert result.source == "AKShare"
        assert result.update_time == datetime(2024, 1, 15, 9, 30, 1)

    @patch("src.akshare_source.ak.fund_etf_spot_em")
    def test_fetch_159501(self, mock_api: MagicMock, source: AKShareSource) -> None:
        """Test fetching 159501 ETF data."""
        mock_api.return_value = _make_etf_dataframe(
            code="159501", price=1.500, iopv=1.450, update_time="2024-03-20 14:30:00"
        )

        result = source.fetch("159501")

        assert result.code == "159501"
        assert result.price == 1.500
        assert result.iopv == 1.450
        assert result.source == "AKShare"

    @patch("src.akshare_source.ak.fund_etf_spot_em")
    def test_fetch_timeout_raises_data_fetch_error(
        self, mock_api: MagicMock, source: AKShareSource
    ) -> None:
        """Test that TimeoutError is wrapped in DataFetchError."""
        mock_api.side_effect = TimeoutError("Connection timed out")

        with pytest.raises(DataFetchError) as exc_info:
            source.fetch("513500")

        assert exc_info.value.source == "AKShare"
        assert exc_info.value.code == "513500"
        assert "超时" in exc_info.value.reason

    @patch("src.akshare_source.ak.fund_etf_spot_em")
    def test_fetch_connection_error_raises_data_fetch_error(
        self, mock_api: MagicMock, source: AKShareSource
    ) -> None:
        """Test that ConnectionError is wrapped in DataFetchError."""
        mock_api.side_effect = ConnectionError("Failed to connect")

        with pytest.raises(DataFetchError) as exc_info:
            source.fetch("513500")

        assert exc_info.value.source == "AKShare"
        assert exc_info.value.code == "513500"
        assert "连接失败" in exc_info.value.reason

    @patch("src.akshare_source.ak.fund_etf_spot_em")
    def test_fetch_generic_exception_raises_data_fetch_error(
        self, mock_api: MagicMock, source: AKShareSource
    ) -> None:
        """Test that generic exceptions are wrapped in DataFetchError."""
        mock_api.side_effect = RuntimeError("Unexpected error")

        with pytest.raises(DataFetchError) as exc_info:
            source.fetch("513500")

        assert exc_info.value.source == "AKShare"
        assert exc_info.value.code == "513500"
        assert "Unexpected error" in exc_info.value.reason

    @patch("src.akshare_source.ak.fund_etf_spot_em")
    def test_fetch_code_not_found_raises_data_fetch_error(
        self, mock_api: MagicMock, source: AKShareSource
    ) -> None:
        """Test that an unknown ETF code raises DataFetchError."""
        mock_api.return_value = _make_etf_dataframe(code="513500")

        with pytest.raises(DataFetchError) as exc_info:
            source.fetch("999999")

        assert exc_info.value.source == "AKShare"
        assert exc_info.value.code == "999999"
        assert "未找到" in exc_info.value.reason

    @patch("src.akshare_source.ak.fund_etf_spot_em")
    def test_fetch_nan_price_raises_data_fetch_error(
        self, mock_api: MagicMock, source: AKShareSource
    ) -> None:
        """Test that NaN price raises DataFetchError."""
        df = pd.DataFrame(
            [
                {
                    "代码": "513500",
                    "名称": "标普500ETF博时",
                    "最新价": float("nan"),
                    "IOPV实时估值": 2.580,
                    "更新时间": pd.Timestamp("2024-01-15 09:30:01"),
                }
            ]
        )
        mock_api.return_value = df

        with pytest.raises(DataFetchError) as exc_info:
            source.fetch("513500")

        assert "最新价" in exc_info.value.reason

    @patch("src.akshare_source.ak.fund_etf_spot_em")
    def test_fetch_nan_iopv_raises_data_fetch_error(
        self, mock_api: MagicMock, source: AKShareSource
    ) -> None:
        """Test that NaN IOPV raises DataFetchError."""
        df = pd.DataFrame(
            [
                {
                    "代码": "513500",
                    "名称": "标普500ETF博时",
                    "最新价": 2.611,
                    "IOPV实时估值": float("nan"),
                    "更新时间": pd.Timestamp("2024-01-15 09:30:01"),
                }
            ]
        )
        mock_api.return_value = df

        with pytest.raises(DataFetchError) as exc_info:
            source.fetch("513500")

        assert "IOPV" in exc_info.value.reason

    @patch("src.akshare_source.ak.fund_etf_spot_em")
    def test_fetch_none_update_time_uses_current_time(
        self, mock_api: MagicMock, source: AKShareSource
    ) -> None:
        """Test that None update_time falls back to current time."""
        df = pd.DataFrame(
            [
                {
                    "代码": "513500",
                    "名称": "标普500ETF博时",
                    "最新价": 2.611,
                    "IOPV实时估值": 2.580,
                    "更新时间": None,
                }
            ]
        )
        mock_api.return_value = df

        before = datetime.now()
        result = source.fetch("513500")
        after = datetime.now()

        assert before <= result.update_time <= after

    @patch("src.akshare_source.ak.fund_etf_spot_em")
    def test_fetch_source_always_akshare(
        self, mock_api: MagicMock, source: AKShareSource
    ) -> None:
        """Test that source is always marked as 'AKShare'."""
        mock_api.return_value = _make_etf_dataframe()

        result = source.fetch("513500")

        assert result.source == "AKShare"
