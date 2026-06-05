"""Tests for TradingCalendar integration in /trigger endpoint.

Validates Requirements: 7.1, 7.2, 7.3, 7.4, 7.5
"""

from unittest.mock import patch, MagicMock

import pytest

from src.api import app


@pytest.fixture
def client():
    """Flask test client."""
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


class TestTriggerCalendarIntegration:
    """Tests for trading calendar check in /trigger endpoint."""

    @patch("src.api.TradingCalendar")
    @patch("src.api.Monitor")
    @patch("src.api.load_config")
    def test_non_trading_day_returns_skipped(self, mock_load, mock_monitor_cls, mock_calendar_cls, client):
        """Req 7.1, 7.2: Non-trading day without force returns skipped."""
        mock_calendar = MagicMock()
        mock_calendar.is_trading_day.return_value = False
        mock_calendar_cls.return_value = mock_calendar

        response = client.get("/trigger")

        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "skipped"
        assert data["reason"] == "non-trading day"
        mock_monitor_cls.assert_not_called()

    @patch("src.api.TradingCalendar")
    @patch("src.api.Monitor")
    @patch("src.api.load_config")
    def test_force_true_bypasses_calendar(self, mock_load, mock_monitor_cls, mock_calendar_cls, client):
        """Req 7.3: force=true bypasses calendar check entirely."""
        mock_config = MagicMock()
        mock_load.return_value = mock_config
        mock_monitor = MagicMock()
        mock_monitor.run.return_value = []
        mock_monitor_cls.return_value = mock_monitor

        response = client.get("/trigger?force=true")

        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "success"
        mock_calendar_cls.assert_not_called()

    @patch("src.api.TradingCalendar")
    @patch("src.api.Monitor")
    @patch("src.api.load_config")
    def test_force_true_case_insensitive(self, mock_load, mock_monitor_cls, mock_calendar_cls, client):
        """Req 7.3: force=True (mixed case) also bypasses calendar."""
        mock_config = MagicMock()
        mock_load.return_value = mock_config
        mock_monitor = MagicMock()
        mock_monitor.run.return_value = []
        mock_monitor_cls.return_value = mock_monitor

        response = client.get("/trigger?force=True")

        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "success"
        mock_calendar_cls.assert_not_called()

    @patch("src.api.TradingCalendar")
    @patch("src.api.Monitor")
    @patch("src.api.load_config")
    def test_calendar_exception_proceeds_with_monitoring(self, mock_load, mock_monitor_cls, mock_calendar_cls, client):
        """Req 7.4: Calendar exception logs warning and proceeds."""
        mock_calendar = MagicMock()
        mock_calendar.is_trading_day.side_effect = RuntimeError("calendar error")
        mock_calendar_cls.return_value = mock_calendar

        mock_config = MagicMock()
        mock_load.return_value = mock_config
        mock_monitor = MagicMock()
        mock_monitor.run.return_value = []
        mock_monitor_cls.return_value = mock_monitor

        response = client.get("/trigger")

        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "success"
        mock_monitor_cls.assert_called_once()

    @patch("src.api.TradingCalendar")
    @patch("src.api.Monitor")
    @patch("src.api.load_config")
    def test_force_invalid_value_applies_calendar_check(self, mock_load, mock_monitor_cls, mock_calendar_cls, client):
        """Req 7.5: force=yes (not 'true') still applies calendar check."""
        mock_calendar = MagicMock()
        mock_calendar.is_trading_day.return_value = False
        mock_calendar_cls.return_value = mock_calendar

        response = client.get("/trigger?force=yes")

        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "skipped"
        assert data["reason"] == "non-trading day"
        mock_monitor_cls.assert_not_called()

    @patch("src.api.TradingCalendar")
    @patch("src.api.Monitor")
    @patch("src.api.load_config")
    def test_trading_day_proceeds_normally(self, mock_load, mock_monitor_cls, mock_calendar_cls, client):
        """Req 7.1: Trading day proceeds with monitoring."""
        mock_calendar = MagicMock()
        mock_calendar.is_trading_day.return_value = True
        mock_calendar_cls.return_value = mock_calendar

        mock_config = MagicMock()
        mock_load.return_value = mock_config
        mock_monitor = MagicMock()
        mock_monitor.run.return_value = []
        mock_monitor_cls.return_value = mock_monitor

        response = client.get("/trigger")

        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "success"
        mock_calendar_cls.assert_called_once()
        mock_calendar.is_trading_day.assert_called_once()
