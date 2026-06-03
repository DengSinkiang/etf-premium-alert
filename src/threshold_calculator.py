"""Dynamic threshold adjustment based on historical premium averages."""

from src.models import PremiumRule


def calculate_adjusted_thresholds(
    rules: list[PremiumRule],
    historical_rates: list[float],
) -> list[PremiumRule]:
    """
    Compute adjusted premium rules by shifting max_premium values based on
    the historical average premium rate.

    min_ratio and max_ratio remain unchanged.

    Returns new PremiumRule instances (does not mutate originals).
    """
    # Insufficient history → return original rules unchanged
    if len(historical_rates) < 3:
        return rules

    # Compute arithmetic mean
    avg = sum(historical_rates) / len(historical_rates)

    # Baseline = minimum max_premium across all rules
    baseline = min(rule.max_premium for rule in rules)

    # If average is at or below baseline → no adjustment needed
    if avg <= baseline:
        return rules

    # Calculate shift, capped at 5.0, rounded to 2 decimal places
    shift = round(min(avg - baseline, 5.0), 2)

    # Return new rules with shifted max_premium; ratios unchanged
    return [
        PremiumRule(
            max_premium=round(rule.max_premium + shift, 2),
            min_ratio=rule.min_ratio,
            max_ratio=rule.max_ratio,
        )
        for rule in rules
    ]
