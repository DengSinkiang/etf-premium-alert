"""Premium rate calculation module for QDII ETF Premium Monitor."""

import logging

from src.models import PremiumRule

logger: logging.Logger = logging.getLogger("monitor")


def calculate_premium_rate(price: float, iopv: float) -> float | None:
    """计算溢价率。

    公式: round((price - iopv) / iopv * 100, 2)

    当 price 或 iopv 为零、负数或无效类型时返回 None 并记录错误日志。

    Args:
        price: ETF 当前价格。
        iopv: 基金参考净值（IOPV）。

    Returns:
        溢价率百分比（保留两位小数），或 None 表示计算失败。
    """
    # Validate price
    if not isinstance(price, (int, float)):
        logger.error("当前价格无效: %s (类型 %s)", price, type(price).__name__)
        return None
    if price <= 0:
        logger.error("当前价格为零或负数: %s", price)
        return None

    # Validate iopv
    if not isinstance(iopv, (int, float)):
        logger.error("估算净值无效: %s (类型 %s)", iopv, type(iopv).__name__)
        return None
    if iopv <= 0:
        logger.error("估算净值为零或负数: %s", iopv)
        return None

    # Check for special float values (NaN, Inf)
    if price != price or iopv != iopv:  # NaN check
        logger.error("价格或净值为 NaN: price=%s, iopv=%s", price, iopv)
        return None
    if abs(price) == float("inf") or abs(iopv) == float("inf"):
        logger.error("价格或净值为无穷大: price=%s, iopv=%s", price, iopv)
        return None

    premium_rate: float = round((price - iopv) / iopv * 100, 2)
    return premium_rate


def calculate_suggested_buy(
    premium_rate: float,
    remaining_target: float,
    rules: list[PremiumRule],
) -> tuple[int, int]:
    """根据溢价率和规则计算建议买入金额区间。

    规则按 max_premium 升序排列。遍历规则，找到第一个
    premium_rate <= rule.max_premium 的规则，使用该规则的比例计算。
    若溢价率超过所有规则的 max_premium，返回 (0, 0)。
    始终执行取整计算，即使 remaining_target 为零（结果为 (0, 0)）。

    Args:
        premium_rate: 溢价率百分比。
        remaining_target: 剩余目标金额。
        rules: 按 max_premium 升序排列的溢价率买入规则列表。

    Returns:
        (min_buy, max_buy) 建议买入金额区间（整数元）。
    """
    sorted_rules = sorted(rules, key=lambda r: r.max_premium)

    for rule in sorted_rules:
        if premium_rate <= rule.max_premium:
            min_buy = int(remaining_target * rule.min_ratio)
            max_buy = int(remaining_target * rule.max_ratio)
            return (min_buy, max_buy)

    return (0, 0)


def get_suggestion_text(premium_rate: float) -> str:
    """根据溢价率返回操作建议文字。

    - 溢价率 <= 1.0%: "可以买入"
    - 1.0% < 溢价率 < 5.0%: "可以分批买"
    - 溢价率 >= 5.0%: "不建议买"

    Args:
        premium_rate: 溢价率百分比。

    Returns:
        操作建议文字字符串。
    """
    if premium_rate <= 1.0:
        return "可以买入"
    elif premium_rate < 5.0:
        return "可以分批买"
    else:
        return "不建议买"
