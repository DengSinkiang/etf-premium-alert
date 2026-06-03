"""Sell advisor module for tier-based sell signal generation."""

from src.models import SellSuggestion


def evaluate_sell(
    code: str,
    name: str,
    premium_rate: float,
    bought_amount: float,
    target_amount: float,
    sell_threshold: float,
) -> SellSuggestion | None:
    """Evaluate whether a sell suggestion should be generated for an ETF.

    Returns a SellSuggestion if the position is fully built (bought_amount >= target_amount)
    and the current premium_rate strictly exceeds the sell_threshold. Otherwise returns None.

    Tier logic based on excess (premium_rate - sell_threshold):
        - 0 < excess <= 2.0  → sell 15% of bought_amount
        - 2.0 < excess <= 5.0 → sell 30% of bought_amount
        - excess > 5.0        → sell 50% of bought_amount
    """
    # No sell suggestion if position is not fully built
    if bought_amount < target_amount:
        return None

    # No sell suggestion if premium_rate does not strictly exceed threshold
    if premium_rate <= sell_threshold:
        return None

    excess = premium_rate - sell_threshold

    # Determine sell percentage based on tier
    if excess <= 2.0:
        sell_percentage = 0.15
    elif excess <= 5.0:
        sell_percentage = 0.30
    else:
        sell_percentage = 0.50

    sell_amount = bought_amount * sell_percentage

    return SellSuggestion(
        code=code,
        name=name,
        premium_rate=premium_rate,
        sell_percentage=sell_percentage,
        sell_amount=sell_amount,
    )
