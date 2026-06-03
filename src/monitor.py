"""Monitor orchestrator for the QDII ETF Premium Monitor.

Coordinates the full monitoring workflow: config load → data fetch →
calculate → format → notify. Handles per-ETF errors gracefully,
continuing to process remaining ETFs on individual failure.
"""

import logging

from src.akshare_source import AKShareSource
from src.data_source import DataSourceManager
from src.discount_alert import DiscountAlert
from src.formatter import format_plain_text, format_telegram_markdown
from src.haoetf_source import HaoETFSource
from src.models import AppConfig, DiscountAlertResult, MonitorResult
from src.notifier import TelegramNotifier
from src.premium_calculator import (
    calculate_premium_rate,
    calculate_suggested_buy,
    get_suggestion_text,
)
from src.premium_store import PremiumStore
from src.strategy_engine import StrategyEngine

logger = logging.getLogger("monitor")


class Monitor:
    """编排层：协调各模块完成完整监控流程。

    职责包括：
    - 遍历所有 ETF 配置项
    - 调用 DataSourceManager 获取数据
    - 调用 PremiumCalculator 计算溢价率和买入建议
    - 检测折价条件并推送折价提醒
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
        self._discount_alert = DiscountAlert(config)
        self._premium_store = PremiumStore(data_dir=config.data_dir)
        self._strategy = StrategyEngine(config, self._premium_store)

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

        # 策略引擎：卖出建议和多 ETF 对比
        sell_suggestions = self._strategy.get_sell_suggestions(results)
        comparisons = self._strategy.get_comparisons(results)

        # 附加策略输出到纯文本
        strategy_plain = self._format_strategy_plain(sell_suggestions, comparisons)
        if strategy_plain:
            plain_output += "\n" + strategy_plain

        print(plain_output)

        # Telegram 通知
        if self._config.telegram.enabled:
            self._send_telegram_notification(results, sell_suggestions, comparisons)

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

        # 3. 计算建议买入金额（使用动态调整后的阈值）
        adjusted_rules = self._strategy.get_adjusted_rules(etf_config, premium_rate)
        suggested_buy_min, suggested_buy_max = calculate_suggested_buy(
            premium_rate=premium_rate,
            remaining_target=remaining_target,
            rules=adjusted_rules,
        )

        # 4. 获取操作建议文字
        suggestion = get_suggestion_text(premium_rate)

        # 5. 折价检测：触发时通过 Notifier 推送 Telegram 消息
        discount_result = self._discount_alert.check(
            code=code,
            name=name,
            premium_rate=premium_rate,
            price=data.price,
            iopv=data.iopv,
            discount_threshold=etf_config.discount_threshold,
        )
        if discount_result is not None:
            self._send_discount_alert(discount_result)

        # 6. 成交量/换手率条件展示：仅当溢价率 >= alert_threshold 时附带
        volume = None
        turnover_rate = None
        if premium_rate >= self._config.alert_threshold:
            volume = data.volume
            turnover_rate = data.turnover_rate

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
            volume=volume,
            turnover_rate=turnover_rate,
        )

    def _send_telegram_notification(self, results: list[MonitorResult],
                                    sell_suggestions=None, comparisons=None) -> None:
        """发送 Telegram 通知。

        当有错误的 ETF 时，错误信息会包含在通知消息中。
        包含卖出建议和多 ETF 对比推荐。

        Args:
            results: 所有 ETF 的监控结果
            sell_suggestions: 卖出建议列表
            comparisons: 对比推荐列表
        """
        try:
            message = format_telegram_markdown(results)

            # 附加策略输出到 Telegram 消息
            strategy_tg = self._format_strategy_telegram(
                sell_suggestions or [], comparisons or []
            )
            if strategy_tg:
                message += "\n" + strategy_tg

            success = self._notifier.send(message)
            if success:
                logger.info("Telegram 通知发送成功")
            else:
                logger.warning("Telegram 通知发送失败")
        except Exception as e:
            logger.error("Telegram 通知发送时发生未预期错误: %s", e)

    def _send_discount_alert(self, alert: DiscountAlertResult) -> None:
        """发送折价提醒 Telegram 消息。

        推送失败时记录错误日志，不中断监控流程。

        Args:
            alert: 折价提醒结果
        """
        if not self._config.telegram.enabled:
            return

        message = (
            f"📉 *折价提醒*\n\n"
            f"ETF: \\[{alert.code}\\] {alert.name}\n"
            f"折价率: {alert.discount_rate:.2f}%\n"
            f"当前价格: {alert.price}\n"
            f"IOPV: {alert.iopv}"
        )
        try:
            success = self._notifier.send(message)
            if success:
                logger.info("[%s] 折价提醒 Telegram 推送成功", alert.code)
            else:
                logger.error("[%s] 折价提醒 Telegram 推送失败", alert.code)
        except Exception as e:
            logger.error("[%s] 折价提醒 Telegram 推送异常: %s", alert.code, e)

    def _format_strategy_plain(self, sell_suggestions, comparisons) -> str:
        """格式化策略输出纯文本（卖出建议 + 对比推荐）。"""
        lines: list[str] = []

        if sell_suggestions:
            lines.append("=== ⚠️ 卖出建议 ===")
            lines.append("")
            for s in sell_suggestions:
                lines.append(f"[{s.code}] {s.name}")
                lines.append(f"  当前溢价率:   {s.premium_rate:.2f}%")
                lines.append(f"  建议卖出比例: {s.sell_percentage * 100:.0f}%")
                lines.append(f"  建议卖出金额: {s.sell_amount:.0f} 元")
                lines.append("")

        if comparisons:
            lines.append("=== 📊 同类对比推荐 ===")
            lines.append("")
            for c in comparisons:
                lines.append(f"分组: {c.group_name}")
                lines.append(f"  推荐: [{c.recommended_code}] {c.recommended_name} (溢价率: {c.recommended_premium:.2f}%)")
                for alt in c.alternatives:
                    lines.append(f"  其他: [{alt['code']}] {alt['name']} (溢价率: {alt['premium_rate']:.2f}%, 高 {alt['diff']:.2f}pp)")
                lines.append("")

        return "\n".join(lines)

    def _format_strategy_telegram(self, sell_suggestions, comparisons) -> str:
        """格式化策略输出 Telegram MarkdownV2。"""
        from src.formatter import _escape_telegram_markdown

        lines: list[str] = []

        if sell_suggestions:
            lines.append("⚠️ *卖出建议*")
            lines.append("")
            for s in sell_suggestions:
                escaped_code = _escape_telegram_markdown(s.code)
                escaped_name = _escape_telegram_markdown(s.name)
                lines.append(f"*\\[{escaped_code}\\] {escaped_name}*")
                escaped_rate = _escape_telegram_markdown(f"{s.premium_rate:.2f}")
                escaped_pct = _escape_telegram_markdown(f"{s.sell_percentage * 100:.0f}")
                escaped_amt = _escape_telegram_markdown(f"{s.sell_amount:.0f}")
                lines.append(f"`当前溢价率:` {escaped_rate}%")
                lines.append(f"`建议卖出:` {escaped_pct}% \\({escaped_amt} 元\\)")
                lines.append("")

        if comparisons:
            lines.append("📊 *同类对比推荐*")
            lines.append("")
            for c in comparisons:
                escaped_group = _escape_telegram_markdown(c.group_name)
                escaped_rec_code = _escape_telegram_markdown(c.recommended_code)
                escaped_rec_name = _escape_telegram_markdown(c.recommended_name)
                escaped_rec_premium = _escape_telegram_markdown(f"{c.recommended_premium:.2f}")
                lines.append(f"*{escaped_group}*")
                lines.append(f"✅ \\[{escaped_rec_code}\\] {escaped_rec_name} \\({escaped_rec_premium}%\\)")
                for alt in c.alternatives:
                    escaped_alt_code = _escape_telegram_markdown(alt["code"])
                    escaped_alt_name = _escape_telegram_markdown(alt["name"])
                    escaped_alt_premium = _escape_telegram_markdown(f"{alt['premium_rate']:.2f}")
                    escaped_alt_diff = _escape_telegram_markdown(f"{alt['diff']:.2f}")
                    lines.append(f"   \\[{escaped_alt_code}\\] {escaped_alt_name} \\({escaped_alt_premium}%, \\+{escaped_alt_diff}pp\\)")
                lines.append("")

        return "\n".join(lines)
