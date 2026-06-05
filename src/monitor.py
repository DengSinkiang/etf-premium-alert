"""Monitor orchestrator for the QDII ETF Premium Monitor.

Coordinates the full monitoring workflow: config load → data fetch →
calculate → format → notify. Handles per-ETF errors gracefully,
continuing to process remaining ETFs on individual failure.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.akshare_source import AKShareSource
from src.data_source import DataSourceManager
from src.discount_alert import DiscountAlert
from src.formatter import format_compact_telegram, format_plain_text, format_telegram_markdown, format_trend_indicator, format_buy_suggestion_with_lots
from src.haoetf_source import HaoETFSource
from src.exceptions import StoreError
from src.models import AppConfig, DiscountAlertResult, ETFConfig, MonitorResult, TrendInfo
from src.notifier import TelegramNotifier
from src.position_store import PositionStore
from src.premium_calculator import (
    calculate_premium_rate,
    calculate_suggested_buy,
    get_suggestion_text,
)
from src.premium_store import PremiumStore
from src.status_store import StatusStore
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

    _THREAD_POOL_MAX_WORKERS: int = 10
    _PIPELINE_TIMEOUT_SECONDS: int = 30

    def __init__(self, config: AppConfig, quiet_mode: bool = True) -> None:
        """初始化 Monitor。

        Args:
            config: 应用程序完整配置对象
            quiet_mode: 是否启用安静模式（默认启用）。启用后，无操作信号时不推送通知。
        """
        self._config = config
        self._quiet_mode = quiet_mode
        self._akshare_source = AKShareSource()
        self._data_source_manager = DataSourceManager(
            primary=self._akshare_source,
            fallback=HaoETFSource(),
        )
        self._notifier = TelegramNotifier(config.telegram)
        self._discount_alert = DiscountAlert(config)
        self._premium_store = PremiumStore(data_dir=config.data_dir)
        self._position_store = PositionStore(data_dir=config.data_dir)
        self._status_store = StatusStore(data_dir=config.data_dir)
        self._strategy = StrategyEngine(config, self._premium_store)
        self._cycle_discount_alerts: list[DiscountAlertResult] = []

    def run(self) -> list[MonitorResult]:
        """执行完整监控流程，返回所有 ETF 的监控结果。

        流程：
        1. 清除 AKShare 缓存，确保本周期获取新数据
        2. 使用 ThreadPoolExecutor 并发处理所有 ETF
        3. 收集结果，保持配置顺序
        4. 构建趋势信息映射和折价提醒列表
        5. 格式化所有结果并输出（含趋势指标和手数建议）
        6. 根据安静模式和操作信号决定 Telegram 推送行为

        Returns:
            所有 ETF 的 MonitorResult 列表
        """
        logger.info("开始执行监控流程")

        # Reset per-cycle cache so the first fetch triggers a fresh API call
        self._akshare_source.invalidate_cache()

        # Reset per-cycle discount alerts tracker
        self._cycle_discount_alerts: list[DiscountAlertResult] = []

        results: list[MonitorResult] = self._process_etfs_parallel()

        # Track status and consecutive failures
        self._update_status(results)

        # Check for newly full positions and alert
        for result in results:
            if result.error is None and result.remaining_target == 0 and result.target_amount > 0:
                # Only alert if we haven't already (check status store)
                status = self._status_store.get_status()
                etf_st = status.get("etf_status", {}).get(result.code, {})
                if not etf_st.get("full_position_alerted", False):
                    self._send_full_position_alert(result.code, result.name, result.bought_amount, result.target_amount)
                    # Mark as alerted in status
                    etf_st["full_position_alerted"] = True
                    status.setdefault("etf_status", {})[result.code] = etf_st
                    self._status_store._write(status)

        # Annotate group comparisons inline
        self._annotate_group_comparisons(results)

        # Build trend_map from results
        trend_map = {r.code: r.trend_info for r in results if r.trend_info is not None}

        # 策略引擎：卖出建议和多 ETF 对比
        sell_suggestions = self._strategy.get_sell_suggestions(results)
        comparisons = self._strategy.get_comparisons(results)

        # 格式化并输出到标准输出（含趋势指标和手数建议）
        plain_output = self._format_plain_text_with_enhancements(results, trend_map, sell_suggestions)

        # 附加策略输出到纯文本
        strategy_plain = self._format_strategy_plain(sell_suggestions, comparisons)
        if strategy_plain:
            plain_output += "\n" + strategy_plain

        print(plain_output)

        # Telegram 通知：根据安静模式决定推送行为
        if self._config.telegram.enabled:
            has_signal = self._has_actionable_signal(
                results, sell_suggestions, self._cycle_discount_alerts
            )

            if self._quiet_mode and not has_signal:
                logger.info("quiet mode: no actionable signals")
            elif self._quiet_mode and has_signal:
                # Quiet mode with actionable signal: use compact format
                self._send_compact_telegram(
                    results, trend_map, sell_suggestions, self._cycle_discount_alerts
                )
            else:
                # --no-quiet mode: send full format
                self._send_telegram_notification(results, sell_suggestions, comparisons)

        logger.info("监控流程执行完毕，共处理 %d 只 ETF", len(results))
        return results

    def _process_etfs_parallel(self) -> list[MonitorResult]:
        """并发处理所有 ETF，保持配置顺序返回结果。

        如果 ThreadPoolExecutor 创建失败，回退到顺序处理。

        Returns:
            所有 ETF 的 MonitorResult 列表，顺序与 config.etfs 一致
        """
        etf_configs = self._config.etfs
        num_etfs = len(etf_configs)

        try:
            executor = ThreadPoolExecutor(max_workers=self._THREAD_POOL_MAX_WORKERS)
        except Exception as e:
            logger.warning(
                "ThreadPoolExecutor 创建失败，回退到顺序处理: %s", e
            )
            return self._process_etfs_sequential()

        results: list[MonitorResult | None] = [None] * num_etfs

        try:
            # Submit all pipelines, tracking index for order preservation
            future_to_index = {}
            for i, etf_config in enumerate(etf_configs):
                future = executor.submit(self._process_etf, etf_config)
                future_to_index[future] = i

            # Collect results with per-pipeline timeout
            for future in as_completed(future_to_index):
                idx = future_to_index[future]
                etf_config = etf_configs[idx]
                try:
                    result = future.result(timeout=self._PIPELINE_TIMEOUT_SECONDS)
                    results[idx] = result
                except TimeoutError:
                    logger.error(
                        "[%s] ETF 处理超时 (%ds)",
                        etf_config.code,
                        self._PIPELINE_TIMEOUT_SECONDS,
                    )
                    results[idx] = MonitorResult(
                        code=etf_config.code,
                        name=etf_config.name,
                        price=None,
                        iopv=None,
                        premium_rate=None,
                        target_amount=etf_config.target_amount,
                        bought_amount=etf_config.bought_amount,
                        remaining_target=etf_config.target_amount - etf_config.bought_amount,
                        suggested_buy_min=None,
                        suggested_buy_max=None,
                        suggestion=None,
                        source=None,
                        update_time=None,
                        error="处理超时",
                    )
                except Exception as e:
                    logger.error(
                        "[%s] ETF 处理异常: %s", etf_config.code, e
                    )
                    results[idx] = MonitorResult(
                        code=etf_config.code,
                        name=etf_config.name,
                        price=None,
                        iopv=None,
                        premium_rate=None,
                        target_amount=etf_config.target_amount,
                        bought_amount=etf_config.bought_amount,
                        remaining_target=etf_config.target_amount - etf_config.bought_amount,
                        suggested_buy_min=None,
                        suggested_buy_max=None,
                        suggestion=None,
                        source=None,
                        update_time=None,
                        error=str(e),
                    )
        finally:
            executor.shutdown(wait=False)

        # Type narrowing: all slots should be filled
        return [r for r in results if r is not None]

    def _process_etfs_sequential(self) -> list[MonitorResult]:
        """顺序处理所有 ETF（ThreadPoolExecutor 创建失败时的回退方案）。

        Returns:
            所有 ETF 的 MonitorResult 列表
        """
        results: list[MonitorResult] = []
        for etf_config in self._config.etfs:
            result = self._process_etf(etf_config)
            results.append(result)
        return results

    def _process_etf(self, etf_config) -> MonitorResult:
        """处理单只 ETF 的完整监控流程。

        Thread Safety:
            This method is called concurrently from ThreadPoolExecutor threads.
            It is safe for parallel execution because:
            - AKShareSource._df_cache: read-only after pre-fetch populates it
              (invalidate_cache is called before threads launch).
            - PremiumStore.save()/query(): each ETF operates on its own file
              ({code}.json), so no cross-file contention exists.
            - StrategyEngine.get_adjusted_rules(): delegates to PremiumStore
              with per-ETF file isolation.
            - DiscountAlert.check(): _alerted_codes set is protected by a
              threading.Lock to prevent duplicate alerts under concurrency.
            - TelegramNotifier.send(): stateless HTTP POST using only immutable
              config; concurrent sends to Telegram API are independent.

        Args:
            etf_config: 单只 ETF 的配置

        Returns:
            MonitorResult 对象（成功或包含错误信息）
        """
        code = etf_config.code
        name = etf_config.name
        target_amount = etf_config.target_amount
        bought_amount = self._compute_effective_bought_amount(etf_config)
        remaining_target = max(0.0, target_amount - bought_amount)

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

        # 2.5 获取趋势信息
        trend_info = self._get_trend_info(code, premium_rate)

        # 2.6 计算溢价率分位（近30天）
        percentile = self._get_percentile(code, premium_rate)

        # 3. 计算建议买入金额（使用动态调整后的阈值）
        adjusted_rules = self._strategy.get_adjusted_rules(etf_config, premium_rate)
        suggested_buy_min, suggested_buy_max = calculate_suggested_buy(
            premium_rate=premium_rate,
            remaining_target=remaining_target,
            rules=adjusted_rules,
        )

        # 4. 获取操作建议文字（基于动态规则匹配结果 + 分位描述）
        if suggested_buy_min > 0:
            if suggested_buy_min >= remaining_target * 0.5:
                suggestion = "可以买入"
            else:
                suggestion = "可以分批买"
        else:
            suggestion = get_suggestion_text(premium_rate)

        # 附加溢价率环境描述
        if percentile is not None:
            if percentile >= 75:
                suggestion += f"（历史{percentile}%分位，偏高）"
            elif percentile >= 50:
                suggestion += f"（历史{percentile}%分位，中等）"
            elif percentile >= 25:
                suggestion += f"（历史{percentile}%分位，偏低）"
            else:
                suggestion += f"（历史{percentile}%分位，低位）"

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
            self._cycle_discount_alerts.append(discount_result)

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
            trend_info=trend_info,
            percentile=percentile,
        )

    def _compute_effective_bought_amount(self, etf_config: ETFConfig) -> float:
        """Compute effective bought amount from config + recorded transactions.

        Delegates to PositionStore.compute_effective_amount which computes:
        config.bought_amount + sum(buys) - sum(sells), clamped to >= 0.

        On StoreError (corrupted JSON or I/O failure), falls back to
        config.bought_amount to avoid breaking the monitoring flow.

        Args:
            etf_config: The ETF configuration object.

        Returns:
            The effective bought amount (>= 0).
        """
        try:
            return self._position_store.compute_effective_amount(
                etf_config.code, etf_config.bought_amount
            )
        except StoreError as e:
            logger.warning(
                "[%s] PositionStore 读取失败，使用配置中的 bought_amount: %s",
                etf_config.code,
                e,
            )
            return etf_config.bought_amount

    def _send_full_position_alert(self, code: str, name: str, bought: float, target: float) -> None:
        """发送仓位满仓提醒。仅在 Telegram 启用时发送。

        Args:
            code: ETF 代码
            name: ETF 名称
            bought: 实际持仓金额
            target: 目标仓位金额
        """
        if not self._config.telegram.enabled:
            return

        message = f"🎉 {name}（{code}）目标仓位已满\n持仓: {bought} 元 / 目标: {target} 元\n后续将只关注卖出信号"
        try:
            self._notifier.send(message)
            logger.info("[%s] 满仓提醒已推送", code)
        except Exception as e:
            logger.error("[%s] 满仓提醒推送失败: %s", code, e)

    def _get_percentile(self, code: str, current_premium: float) -> int | None:
        """Calculate the percentile rank of current premium in 30-day history.

        Returns None if fewer than 5 historical records exist.
        """
        try:
            records = self._premium_store.query(code, lookback_days=30)
        except StoreError:
            return None

        if len(records) < 5:
            return None

        historical = [r.premium_rate for r in records]
        count_below = sum(1 for h in historical if h < current_premium)
        percentile = int(count_below / len(historical) * 100)
        return percentile

    def _annotate_group_comparisons(self, results: list[MonitorResult]) -> None:
        """Annotate each result with group comparison text.

        For each group, find the ETF with lowest premium rate and annotate:
        - Lowest: "✅本组最优"
        - Others: "比最优高 +X.XXpp"
        """
        # Build groups: group_name -> list of results with valid premium
        groups: dict[str, list[MonitorResult]] = {}
        for r in results:
            if r.premium_rate is None:
                continue
            # Find group from config
            etf_config = next(
                (etf for etf in self._config.etfs if etf.code == r.code), None
            )
            if etf_config is None or etf_config.group is None:
                continue
            groups.setdefault(etf_config.group, []).append(r)

        # Annotate each group
        for group_results in groups.values():
            if len(group_results) < 2:
                continue

            # Find minimum premium in group
            min_premium = min(r.premium_rate for r in group_results)

            for r in group_results:
                if r.premium_rate == min_premium:
                    r.group_comparison = "✅本组最优"
                else:
                    diff = r.premium_rate - min_premium
                    r.group_comparison = f"比最优高 +{diff:.2f}pp"

    def _update_status(self, results: list[MonitorResult]) -> None:
        """Update status tracking and send alert on consecutive failures.

        Records success/failure per ETF. If any ETF has 3+ consecutive
        failures, sends a one-time Telegram alert.
        """
        _FAILURE_THRESHOLD = 3

        for result in results:
            try:
                if result.error is None:
                    self._status_store.record_success(result.code)
                else:
                    count = self._status_store.record_failure(result.code)
                    if count == _FAILURE_THRESHOLD and self._config.telegram.enabled:
                        self._notifier.send(
                            f"⚠️ 数据源持续异常\n\n"
                            f"ETF: {result.name}（{result.code}）\n"
                            f"已连续 {count} 次获取失败\n"
                            f"最近错误: {result.error}"
                        )
            except Exception as e:
                logger.warning("[%s] 状态记录失败: %s", result.code, e)

    def _get_trend_info(self, code: str, current_premium: float) -> TrendInfo | None:
        """Compare current premium against most recent PremiumStore record.

        Uses PremiumStore.query(code, lookback_days=1) to retrieve recent
        records. The last item in the returned list is the most recent.

        Args:
            code: ETF code.
            current_premium: The current premium rate percentage.

        Returns:
            TrendInfo with arrow and delta, or None if no previous record
            exists or a store error occurs.
        """
        try:
            records = self._premium_store.query(code, lookback_days=1)
        except StoreError as e:
            logger.warning("[%s] PremiumStore 读取失败，跳过趋势指标: %s", code, e)
            return None

        if not records:
            return None

        previous_record = records[-1]
        delta = current_premium - previous_record.premium_rate

        if delta >= 0.01:
            arrow = "↑"
        elif delta <= -0.01:
            arrow = "↓"
        else:
            arrow = "→"

        return TrendInfo(arrow=arrow, delta=delta, previous_rate=previous_record.premium_rate)

    def _has_actionable_signal(
        self,
        results: list[MonitorResult],
        sell_suggestions: list,
        discount_alerts: list[DiscountAlertResult],
    ) -> bool:
        """判断本次监控周期是否存在可操作信号。

        Returns True if any of the following conditions hold:
        - Any result has suggested_buy_min > 0 (and suggested_buy_min is not None)
        - sell_suggestions is non-empty
        - discount_alerts is non-empty

        Args:
            results: 所有 ETF 的监控结果
            sell_suggestions: 卖出建议列表
            discount_alerts: 折价提醒列表

        Returns:
            True if at least one actionable signal is detected.
        """
        if sell_suggestions:
            return True
        if discount_alerts:
            return True
        for result in results:
            if result.suggested_buy_min is not None and result.suggested_buy_min > 0:
                return True
        return False

    def _format_plain_text_with_enhancements(
        self,
        results: list[MonitorResult],
        trend_map: dict[str, TrendInfo],
        sell_suggestions: list,
    ) -> str:
        """格式化增强版纯文本输出，包含趋势指标和手数建议。

        在原有纯文本基础上：
        - 溢价率后附加趋势箭头和变化量
        - 买入建议以手数格式显示

        Args:
            results: 所有 ETF 的监控结果
            trend_map: code -> TrendInfo 映射
            sell_suggestions: 卖出建议列表

        Returns:
            格式化后的纯文本字符串
        """
        from datetime import datetime as dt

        lines: list[str] = []

        # Header with timestamp
        header_time = dt.now().strftime("%Y-%m-%d %H:%M:%S")
        lines.append(f"=== QDII ETF 溢价率监控 ({header_time}) ===")
        lines.append("")

        for i, result in enumerate(results):
            if i > 0:
                lines.append("---")
                lines.append("")

            if result.error is not None:
                # Error case
                lines.append(f"[{result.code}] {result.name}")
                lines.append(f"  错误: {result.error}")
                lines.append("")
            else:
                # Normal case with all fields
                lines.append(f"[{result.code}] {result.name}")
                lines.append(f"  当前价格:     {result.price}")
                lines.append(f"  估算净值:     {result.iopv}")

                # 溢价率 + 趋势指标
                trend = trend_map.get(result.code)
                trend_str = format_trend_indicator(trend)
                if trend_str:
                    lines.append(f"  当前溢价率:   {result.premium_rate}% {trend_str}")
                else:
                    lines.append(f"  当前溢价率:   {result.premium_rate}%")

                lines.append(f"  目标仓位:     {result.target_amount} 元")
                lines.append(f"  已买金额:     {result.bought_amount} 元")
                lines.append(f"  剩余目标:     {result.remaining_target} 元")

                # 买入建议以手数格式显示
                if result.suggested_buy_min is not None and result.suggested_buy_max is not None:
                    lot_suggestion = format_buy_suggestion_with_lots(
                        result.suggested_buy_min, result.suggested_buy_max, result.price
                    )
                    lines.append(f"  {lot_suggestion}")
                else:
                    lines.append(f"  建议买入区间: {result.suggested_buy_min} ~ {result.suggested_buy_max} 元")

                lines.append(f"  操作建议:     {result.suggestion}")
                lines.append(f"  数据来源:     {result.source}")

                from src.formatter import _format_update_time
                lines.append(f"  更新时间:     {_format_update_time(result.update_time)}")
                # 成交量/换手率展示（仅高溢价时有值）
                if result.volume is not None or result.turnover_rate is not None:
                    from src.formatter import format_volume_info_plain
                    lines.append(f"  {format_volume_info_plain(result.volume, result.turnover_rate)}")
                lines.append("")

        return "\n".join(lines)

    def _send_compact_telegram(
        self,
        results: list[MonitorResult],
        trend_map: dict[str, TrendInfo],
        sell_suggestions: list,
        discount_alerts: list[DiscountAlertResult],
    ) -> None:
        """发送紧凑格式 Telegram 通知。

        Args:
            results: 所有 ETF 的监控结果
            trend_map: code -> TrendInfo 映射
            sell_suggestions: 卖出建议列表
            discount_alerts: 折价提醒列表
        """
        try:
            message = format_compact_telegram(
                results, trend_map, sell_suggestions, discount_alerts
            )
            success = self._notifier.send(message)
            if success:
                logger.info("Telegram 紧凑格式通知发送成功")
            else:
                logger.warning("Telegram 紧凑格式通知发送失败")
        except Exception as e:
            logger.error("Telegram 紧凑格式通知发送时发生未预期错误: %s", e)

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
