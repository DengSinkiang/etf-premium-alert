"""Unit tests for TradingCalendar."""

from datetime import date
from unittest.mock import MagicMock

from src import trading_calendar
from src.trading_calendar import TradingCalendar


def test_weekday_non_holiday_is_trading_day(monkeypatch):
    monkeypatch.setattr(trading_calendar, "_HAS_CHINESE_CALENDAR", True)
    mock_calendar = MagicMock()
    mock_calendar.is_holiday.return_value = False
    monkeypatch.setattr(trading_calendar, "chinese_calendar", mock_calendar, raising=False)

    assert TradingCalendar().is_trading_day(date(2024, 1, 15)) is True


def test_weekday_holiday_is_not_trading_day(monkeypatch):
    monkeypatch.setattr(trading_calendar, "_HAS_CHINESE_CALENDAR", True)
    mock_calendar = MagicMock()
    mock_calendar.is_holiday.return_value = True
    monkeypatch.setattr(trading_calendar, "chinese_calendar", mock_calendar, raising=False)

    assert TradingCalendar().is_trading_day(date(2024, 1, 1)) is False


def test_weekend_workday_is_not_trading_day(monkeypatch):
    monkeypatch.setattr(trading_calendar, "_HAS_CHINESE_CALENDAR", True)
    mock_calendar = MagicMock()
    mock_calendar.is_holiday.return_value = False
    monkeypatch.setattr(trading_calendar, "chinese_calendar", mock_calendar, raising=False)

    assert TradingCalendar().is_trading_day(date(2024, 2, 4)) is False
