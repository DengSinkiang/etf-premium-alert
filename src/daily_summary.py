"""Daily summary report generator for the QDII ETF Premium Monitor."""

import logging
from datetime import date, datetime, timezone, timedelta

from src.config import AppConfig
from src.models import (
    DailySummaryReport,
    ETFConfig,
    ETFDailySummary,
    PremiumRecord,
)
from src.premium_store import PremiumStore

logger = logging.getLogger(__name__)

# Beijing timezone (UTC+8)
_BEIJING_TZ = timezone(timedelta(hours=8))


class DailySummaryReporter:
    """每日摘要报告生成器。

    从 PremiumStore 读取当日溢价率记录，汇总生成每只 ETF 的
    最高/最低/收盘溢价率和买入/卖出触发情况。
    """

    def __init__(self, config: AppConfig, premium_store: PremiumStore) -> None:
        self._config = config
        self._premium_store = premium_store

    def generate(self, target_date: date | None = None) -> DailySummaryReport:
        """生成指定日期的摘要报告。

        Args:
            target_date: 目标日期，默认为今天（北京时间）

        Returns:
            DailySummaryReport 摘要报告对象
        """
        if target_date is None:
            now_beijing = datetime.now(_BEIJING_TZ)
            target_date = now_beijing.date()

        summaries: list[ETFDailySummary] = []

        for etf_config in self._config.etfs:
            summary = self._generate_etf_summary(etf_config, target_date)
            summaries.append(summary)

        return DailySummaryReport(
            date=target_date.strftime("%Y-%m-%d"),
            summaries=summaries,
        )

    def _generate_etf_summary(
        self, etf_config: ETFConfig, target_date: date
    ) -> ETFDailySummary:
        """生成单只 ETF 的每日摘要。"""
        try:
            records = self._get_daily_records(etf_config.code, target_date)
        except Exception as e:
            logger.error(
                "读取 %s 当日记录失败: %s", etf_config.code, str(e)
            )
            return ETFDailySummary(
                code=etf_config.code,
                name=etf_config.name,
                max_premium=None,
                min_premium=None,
                close_premium=None,
                buy_triggered=False,
                sell_triggered=False,
                status="read_error",
            )

        if not records:
            return ETFDailySummary(
                code=etf_config.code,
                name=etf_config.name,
                max_premium=None,
                min_premium=None,
                close_premium=None,
                buy_triggered=False,
                sell_triggered=False,
                status="no_data",
            )

        # Calculate max/min/close premium
        premium_rates = [r.premium_rate for r in records]
        max_premium = max(premium_rates)
        min_premium = min(premium_rates)
        # Records are sorted ascending by timestamp from PremiumStore.query()
        close_premium = records[-1].premium_rate

        # Check buy/sell triggers
        buy_triggered = self._check_buy_triggered(records, etf_config)
        sell_triggered = self._check_sell_triggered(records, etf_config)

        return ETFDailySummary(
            code=etf_config.code,
            name=etf_config.name,
            max_premium=max_premium,
            min_premium=min_premium,
            close_premium=close_premium,
            buy_triggered=buy_triggered,
            sell_triggered=sell_triggered,
            status="normal",
        )

    def _get_daily_records(
        self, code: str, target_date: date
    ) -> list[PremiumRecord]:
        """从 PremiumStore 读取指定日期的所有记录（北京时间 00:00-23:59）。

        Args:
            code: ETF 代码
            target_date: 目标日期

        Returns:
            当日所有记录列表，按时间戳升序排列

        Raises:
            Exception: PremiumStore 读取失败时抛出
        """
        # Query with enough lookback to cover the target date
        # Use 2 days lookback to ensure we capture the target date's records
        today = datetime.now().date()
        lookback_days = (today - target_date).days + 1
        if lookback_days < 1:
            lookback_days = 1

        all_records = self._premium_store.query(code, lookback_days)

        # Filter to only records from the target date (Beijing time 00:00:00 - 23:59:59)
        daily_records = []
        for record in all_records:
            # Convert record timestamp to Beijing time date for comparison
            # PremiumStore stores timestamps as local system time
            record_date = record.timestamp.date()
            if record_date == target_date:
                daily_records.append(record)

        return daily_records

    def _check_buy_triggered(
        self, records: list[PremiumRecord], etf_config: ETFConfig
    ) -> bool:
        """判断当日是否有记录满足 premium_rules 买入条件。

        买入触发条件：存在至少一条记录的 premium_rate 满足任一
        premium_rule 的 max_premium 上限（即 premium_rate <= max_premium）。

        Args:
            records: 当日所有记录
            etf_config: ETF 配置

        Returns:
            True 如果触发过买入建议
        """
        if not etf_config.premium_rules:
            return False

        for record in records:
            for rule in etf_config.premium_rules:
                if record.premium_rate <= rule.max_premium:
                    return True

        return False

    def _check_sell_triggered(
        self, records: list[PremiumRecord], etf_config: ETFConfig
    ) -> bool:
        """判断当日是否有记录超过 sell_threshold。

        卖出触发条件：存在至少一条记录的 premium_rate > sell_threshold。

        Args:
            records: 当日所有记录
            etf_config: ETF 配置

        Returns:
            True 如果触发过卖出建议
        """
        for record in records:
            if record.premium_rate > etf_config.sell_threshold:
                return True

        return False
