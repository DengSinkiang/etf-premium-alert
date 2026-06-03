"""Comparison Engine for multi-ETF group comparison.

Compares premium rates across ETFs tracking the same index and recommends
the lowest-premium option within each group.
"""

from src.models import ComparisonResult


def compare_group(
    group_name: str,
    etf_premiums: list[dict],
) -> ComparisonResult | None:
    """Compare ETFs within a group and recommend the lowest-premium option.

    Args:
        group_name: Name of the ETF group (e.g. "sp500").
        etf_premiums: List of dicts with keys: code, name, premium_rate.
            premium_rate may be None for errored ETFs.

    Returns:
        ComparisonResult with recommendation, or None if fewer than 2 valid ETFs.
    """
    # Filter out entries where premium_rate is None (errored ETFs)
    valid = [entry for entry in etf_premiums if entry.get("premium_rate") is not None]

    # Need at least 2 valid ETFs to make a comparison
    if len(valid) < 2:
        return None

    # Sort by premium_rate ascending; stable sort preserves config order for ties
    sorted_entries = sorted(valid, key=lambda e: e["premium_rate"])

    # Recommended = first after sort (lowest premium)
    recommended = sorted_entries[0]

    # Alternatives = remaining entries with diff calculated
    alternatives = []
    for entry in sorted_entries[1:]:
        alternatives.append(
            {
                "code": entry["code"],
                "name": entry["name"],
                "premium_rate": entry["premium_rate"],
                "diff": entry["premium_rate"] - recommended["premium_rate"],
            }
        )

    return ComparisonResult(
        group_name=group_name,
        recommended_code=recommended["code"],
        recommended_name=recommended["name"],
        recommended_premium=recommended["premium_rate"],
        alternatives=alternatives,
    )
