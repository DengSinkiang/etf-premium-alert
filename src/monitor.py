"""Monitor orchestrator for the QDII ETF Premium Monitor.

Coordinates the full monitoring workflow: config load → data fetch →
calculate → format → notify. Handles per-ETF errors gracefully,
continuing to process remaining ETFs on individual failure.
"""

import logging

from src.akshare_source import AKShareSource
from src.data_source import DataSourceManager
from src.formatter import format_plain_text, format_telegram_markdown
from src.haoetf_source import HaoETFSource
from src.models import AppConfig, MonitorResult
from src.notifier import TelegramNotifier
from src.premium_calculator import (
    calculate_premium_rate,
    calculate_suggested_buy,
    get_suggestion_text,
)

logger = logging.getLogger("monitor")


class Monitor:
    """编排层：协调各模块完成完整监控流程。

    职责包括：
    - 遍历所有 ETF 配置项
    - 调用 DataSourceManager 获取数据
    - 调用 PremiumCalculator 计算溢价率和买入建议
    - 格式化输出并发送 Telegram 通知
    - 处理 per-ETF 错误，不中断整体流程
    """

    def __init__(self, config: AppConfig) -> None:
        """初始化 Monitor。

        Args:
            config: 应用程序完整配置对象
        """
        self._config = config
        self._data_source_manager = DataSourceManager(
            primary=AKShareSource(),
            fallback=HaoETFSource(),
        )
        self._notifier = TelegramNotifier(config.telegram)

    def run(self) -> list[MonitorResult]:
        """执行完整监控流程，返回所有 ETF 的监控结果。

        流程：
        1. 遍历每只 ETF，获取数据、计算溢价率、生成买入建议
        2. 单只 ETF 失败时记录错误并继续处理剩余 ETF
        3. 格式化所有结果并输出
        4. 如果 Telegram 已启用，发送通知

        Returns:
            所有 ETF 的 MonitorResult 列表
        """
        logger.info("开始执行监控流程")
        results: list[MonitorResult] = []

        for etf_config in self._config.etfs:
            result = self._process_etf(etf_config)
            results.append(result)

        # 格式化并输出到标准输出
        plain_output = format_plain_text(results)
        print(plain_output)

        # Telegram 通知
        if self._config.telegram.enabled:
            self._send_telegram_notification(results)

        logger.info("监控流程执行完毕，共处理 %d 只 ETF", len(results))
        return results

    def _process_etf(self, etf_config) -> MonitorResult:
        """处理单只 ETF 的完整监控流程。

        Args:
            etf_config: 单只 ETF 的配置

        Returns:
            MonitorResult 对象（成功或包含错误信息）
        """
        code = etf_config.code
        name = etf_config.name
        target_amount = etf_config.target_amount
        bought_amount = etf_config.bought_amount
        remaining_target = target_amount - bought_amount

        logger.info("开始处理 ETF: [%s] %s", code, name)

        # 1. 获取数据
        try:
            data, error_reason = self._data_source_manager.get_etf_data(code)
        except Exception as e:
            logger.error("获取 %s 数据时发生未预期错误: %s", code, e)
            return MonitorResult(
                code=code,
                name=name,
                price=None,
                iopv=None,
                premium_rate=None,
                target_amount=target_amount,
                bought_amount=bought_amount,
                remaining_target=remaining_target,
                suggested_buy_min=None,
                suggested_buy_max=None,
                suggestion=None,
                source=None,
                update_time=None,
                error=f"数据获取失败: {e}",
            )

        if data is None:
            error_msg = error_reason if error_reason else f"所有数据源获取 {code} 均失败"
            logger.error(error_msg)
            return MonitorResult(
                code=code,
                name=name,
                price=None,
                iopv=None,
                premium_rate=None,
                target_amount=target_amount,
                bought_amount=bought_amount,
                remaining_target=remaining_target,
                suggested_buy_min=None,
                suggested_buy_max=None,
                suggestion=None,
                source=None,
                update_time=None,
                error=error_msg,
            )

        # 2. 计算溢价率
        premium_rate = calculate_premium_rate(data.price, data.iopv)
        if premium_rate is None:
            error_msg = f"溢价率计算失败: price={data.price}, iopv={data.iopv}"
            logger.error("[%s] %s", code, error_msg)
            return MonitorResult(
                code=code,
                name=name,
                price=data.price,
                iopv=data.iopv,
                premium_rate=None,
                target_amount=target_amount,
                bought_amount=bought_amount,
                remaining_target=remaining_target,
                suggested_buy_min=None,
                suggested_buy_max=None,
                suggestion=None,
                source=data.source,
                update_time=data.update_time,
                error=error_msg,
            )

        # 3. 计算建议买入金额
        suggested_buy_min, suggested_buy_max = calculate_suggested_buy(
            premium_rate=premium_rate,
            remaining_target=remaining_target,
            rules=etf_config.premium_rules,
        )

        # 4. 获取操作建议文字
        suggestion = get_suggestion_text(premium_rate)

        logger.info(
            "[%s] 溢价率=%.2f%%, 建议买入=%d~%d元, 建议=%s",
            code,
            premium_rate,
            suggested_buy_min,
            suggested_buy_max,
            suggestion,
        )

        return MonitorResult(
            code=code,
            name=name,
            price=data.price,
            iopv=data.iopv,
            premium_rate=premium_rate,
            target_amount=target_amount,
            bought_amount=bought_amount,
            remaining_target=remaining_target,
            suggested_buy_min=suggested_buy_min,
            suggested_buy_max=suggested_buy_max,
            suggestion=suggestion,
            source=data.source,
            update_time=data.update_time,
            error=None,
        )

    def _send_telegram_notification(self, results: list[MonitorResult]) -> None:
        """发送 Telegram 通知。

        当有错误的 ETF 时，错误信息会包含在通知消息中。

        Args:
            results: 所有 ETF 的监控结果
        """
        try:
            message = format_telegram_markdown(results)
            success = self._notifier.send(message)
            if success:
                logger.info("Telegram 通知发送成功")
            else:
                logger.warning("Telegram 通知发送失败")
        except Exception as e:
            logger.error("Telegram 通知发送时发生未预期错误: %s", e)
