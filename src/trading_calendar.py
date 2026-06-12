"""Trading calendar module for A-share market trading day detection."""

import logging
from datetime import date, datetime, timezone, timedelta

# Beijing timezone offset (UTC+8)
_BEIJING_TZ = timezone(timedelta(hours=8))

logger = logging.getLogger("monitor")

# Try to import chinese_calendar at module level
try:
    import chinese_calendar
    _HAS_CHINESE_CALENDAR = True
except ImportError:
    _HAS_CHINESE_CALENDAR = False
    logger.warning(
        "chinese_calendar 库导入失败，交易日判断将回退到仅排除周末的基础逻辑"
    )


class TradingCalendar:
    """A 股交易日历，基于 chinese_calendar 库判断交易日。"""

    def is_trading_day(self, date: date | None = None) -> bool:
        """判断指定日期是否为交易日。

        Args:
            date: 待判断的日期，默认为今天（北京时间）

        Returns:
            True 表示交易日，False 表示非交易日
        """
        if date is None:
            date = datetime.now(_BEIJING_TZ).date()

        if _HAS_CHINESE_CALENDAR:
            try:
                return date.weekday() < 5 and not chinese_calendar.is_holiday(date)
            except Exception as e:
                logger.warning(
                    "chinese_calendar.is_holiday() 调用异常: %s，回退到基础逻辑", e
                )
                return self._fallback_check(date)
        else:
            return self._fallback_check(date)

    def _fallback_check(self, date: date) -> bool:
        """回退逻辑：仅排除周六和周日。

        Args:
            date: 待判断的日期

        Returns:
            True 表示周一至周五（weekday 0-4），False 表示周六或周日（weekday 5-6）
        """
        return date.weekday() < 5
