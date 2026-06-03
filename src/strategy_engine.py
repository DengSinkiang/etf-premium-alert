"""Strategy Engine orchestrator for dynamic thresholds, sell signals, and group comparison."""

import logging
from datetime import datetime

from src.comparison_engine import compare_group
from src.exceptions import StoreError
from src.models import (
    AppConfig,
    ComparisonResult,
    ETFConfig,
    MonitorResult,
    PremiumRule,
    SellSuggestion,
)
from src.premium_store import PremiumStore
from src.sell_advisor import evaluate_sell
from src.threshold_calculator import calculate_adjusted_thresholds

logger = logging.getLogger("monitor")


class StrategyEngine:
    """Orchestrator that ties together premium persistence, threshold adjustment,
    sell advisory, and multi-ETF comparison.
    """

    def __init__(self, config: AppConfig, premium_store: PremiumStore) -> None:
        self._config = config
        self._premium_store = premium_store
        # Build a lookup map from ETF code to its configuration
        self._etf_map: dict[str, ETFConfig] = {
            etf.code: etf for etf in config.etfs
        }

    def get_adjusted_rules(
        self, etf_config: ETFConfig, premium_rate: float
    ) -> list[PremiumRule]:
        """Persist current premium rate, query history, and return adjusted rules.

        On any store error, falls back to returning the static premium_rules
        from the ETF configuration unchanged.
        """
        # 1. Persist the current premium rate (handle StoreError gracefully)
        try:
            self._premium_store.save(
                code=etf_config.code,
                premium_rate=premium_rate,
                timestamp=datetime.now(),
            )
        except StoreError as e:
            logger.error("溢价率存储失败 [%s]: %s", etf_config.code, e)
            # Fallback to static rules on write failure
            return etf_config.premium_rules

        # 2. Query historical rates (handle StoreError gracefully)
        try:
            records = self._premium_store.query(
                code=etf_config.code,
                lookback_days=self._config.lookback_days,
            )
        except StoreError as e:
            logger.error("历史溢价率查询失败 [%s]: %s", etf_config.code, e)
            # Fallback to static rules on read failure
            return etf_config.premium_rules

        # 3. Calculate adjusted thresholds
        historical_rates = [record.premium_rate for record in records]
        return calculate_adjusted_thresholds(etf_config.premium_rules, historical_rates)

    def get_sell_suggestions(
        self, results: list[MonitorResult]
    ) -> list[SellSuggestion]:
        """Evaluate sell conditions for all ETFs with valid premium data.

        Iterates through monitor results, looks up each ETF's config to get
        the sell_threshold, and calls evaluate_sell for ETFs with a valid
        premium_rate.
        """
        suggestions: list[SellSuggestion] = []

        for result in results:
            # Skip results without a valid premium rate
            if result.premium_rate is None:
                continue

            # Look up ETF config to get sell_threshold
            etf_config = self._etf_map.get(result.code)
            if etf_config is None:
                continue

            suggestion = evaluate_sell(
                code=result.code,
                name=result.name,
                premium_rate=result.premium_rate,
                bought_amount=result.bought_amount,
                target_amount=result.target_amount,
                sell_threshold=etf_config.sell_threshold,
            )

            if suggestion is not None:
                suggestions.append(suggestion)

        return suggestions

    def get_comparisons(
        self, results: list[MonitorResult]
    ) -> list[ComparisonResult]:
        """Run group comparison across all configured ETF groups.

        Groups ETFs by their config group field (skips ETFs without a group),
        collects premium data from monitor results, and calls compare_group
        for each group.
        """
        # Build groups from config: group_name -> list of ETF codes (in config order)
        groups: dict[str, list[str]] = {}
        for etf_config in self._config.etfs:
            if etf_config.group is None:
                continue
            groups.setdefault(etf_config.group, []).append(etf_config.code)

        # Build a lookup from code to monitor result for quick access
        result_map: dict[str, MonitorResult] = {r.code: r for r in results}

        comparisons: list[ComparisonResult] = []

        for group_name, codes in groups.items():
            # Collect premium data for ETFs in this group
            etf_premiums: list[dict] = []
            for code in codes:
                result = result_map.get(code)
                if result is None:
                    continue
                etf_premiums.append({
                    "code": result.code,
                    "name": result.name,
                    "premium_rate": result.premium_rate,
                })

            # Call compare_group and collect non-None results
            comparison = compare_group(group_name, etf_premiums)
            if comparison is not None:
                comparisons.append(comparison)

        return comparisons
