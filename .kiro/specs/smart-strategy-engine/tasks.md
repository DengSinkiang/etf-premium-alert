# Implementation Plan: Smart Strategy Engine

## Overview

Implement the Smart Strategy Engine by extending the existing QDII ETF Premium Monitor with dynamic threshold adjustment, sell suggestion generation, and multi-ETF comparison. The approach builds components bottom-up: data models → persistence layer → pure-function calculators → orchestrator → formatter → integration into Monitor. Python 3.11+, pytest, and hypothesis are used throughout.

## Tasks

- [x] 1. Extend data models and configuration
  - [x] 1.1 Add new data classes to `src/models.py`
    - Add `PremiumRecord` dataclass (code, premium_rate, timestamp)
    - Add `SellSuggestion` dataclass (code, name, premium_rate, sell_percentage, sell_amount)
    - Add `ComparisonResult` dataclass (group_name, recommended_code, recommended_name, recommended_premium, alternatives)
    - Add `StrategyResult` dataclass (sell_suggestions, comparisons, adjusted_rules_map)
    - Extend `ETFConfig` with `sell_threshold: float = 8.0` and `group: str | None = None`
    - Extend `AppConfig` with `lookback_days: int = 7` and `data_dir: str = "data"`
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [x] 1.2 Extend configuration loader in `src/config.py`
    - Parse optional `lookback_days` (positive int 1–90, default 7) from top-level config
    - Parse optional `data_dir` (string, default "data") from top-level config
    - Parse optional `sell_threshold` (numeric 0.1–50.0, default 8.0) per ETF
    - Parse optional `group` (non-empty string max 64 chars, or None) per ETF; treat empty string as None
    - Add validation: invalid types/out-of-range values print field-specific error to stderr and exit(1)
    - Maintain backward compatibility with existing config.yaml files lacking new fields
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7_

  - [ ]* 1.3 Write unit tests for configuration extension
    - Test default values applied when fields absent
    - Test range validation (lookback_days=0, sell_threshold=-1, group as int)
    - Test backward compatibility with old config format
    - Test empty group string treated as None
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7_

- [x] 2. Implement Premium_Store persistence layer
  - [x] 2.1 Create `src/premium_store.py`
    - Implement `PremiumStore` class with `__init__(data_dir)`, `save(code, premium_rate, timestamp)`, `query(code, lookback_days)`, `_cleanup(code)`
    - File layout: `{data_dir}/{code}.json` with records array
    - `save()`: append record, deduplicate by timestamp (overwrite same-second), call `_cleanup()` to prune >30 days
    - `query()`: return records within lookback window, sorted by timestamp ascending
    - Auto-create data_dir with `os.makedirs(exist_ok=True)`
    - Handle IOError and json.JSONDecodeError gracefully, raise custom `StoreError`
    - _Requirements: 1.1, 1.2, 1.5, 1.6, 1.7_

  - [ ]* 2.2 Write property test for storage idempotency
    - **Property 7: Storage Idempotency**
    - **Validates: Requirements 1.7**

  - [ ]* 2.3 Write property test for storage bounded growth
    - **Property 8: Storage Bounded Growth**
    - **Validates: Requirements 1.6**

  - [ ]* 2.4 Write unit tests for Premium_Store
    - Test save/query round-trip
    - Test corrupted file recovery (malformed JSON)
    - Test query returns only records within lookback window
    - Test timestamp ordering in query results
    - _Requirements: 1.1, 1.2, 1.5, 1.6, 1.7_

- [x] 3. Implement Threshold_Calculator
  - [x] 3.1 Create `src/threshold_calculator.py`
    - Implement `calculate_adjusted_thresholds(rules, historical_rates) -> list[PremiumRule]`
    - If `len(historical_rates) < 3` → return original rules unchanged
    - Compute arithmetic mean of historical_rates
    - Baseline = min(rule.max_premium for rule in rules)
    - If avg <= baseline → return original rules unchanged
    - Shift = min(avg - baseline, 5.0), rounded to 2 decimal places
    - Return new rules with each max_premium += shift; min_ratio and max_ratio unchanged
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.7_

  - [ ]* 3.2 Write property test for threshold shift monotonicity
    - **Property 1: Threshold Shift Monotonicity**
    - **Validates: Requirements 2.2**

  - [ ]* 3.3 Write property test for threshold shift cap bound
    - **Property 2: Threshold Shift Cap Bound**
    - **Validates: Requirements 2.5**

  - [ ]* 3.4 Write property test for ratio preservation
    - **Property 9: Ratio Preservation**
    - **Validates: Requirements 2.7**

  - [ ]* 3.5 Write unit tests for Threshold_Calculator
    - Test < 3 records fallback
    - Test avg below baseline returns original rules
    - Test shift calculation with known values
    - Test cap enforcement at 5.0
    - Test rounding to 2 decimal places
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.7_

- [x] 4. Implement Sell_Advisor
  - [x] 4.1 Create `src/sell_advisor.py`
    - Implement `evaluate_sell(code, name, premium_rate, bought_amount, target_amount, sell_threshold) -> SellSuggestion | None`
    - Return None if bought_amount < target_amount
    - Return None if premium_rate <= sell_threshold
    - Calculate excess = premium_rate - sell_threshold
    - Tier logic: 0 < excess <= 2.0 → 15%, 2.0 < excess <= 5.0 → 30%, excess > 5.0 → 50%
    - Calculate sell_amount = bought_amount * sell_percentage
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.6, 3.7_

  - [ ]* 4.2 Write property test for sell suggestion exclusivity
    - **Property 3: Sell Suggestion Exclusivity**
    - **Validates: Requirements 3.1, 3.4, 3.7**

  - [ ]* 4.3 Write property test for sell tier completeness
    - **Property 4: Sell Tier Completeness**
    - **Validates: Requirements 3.3**

  - [ ]* 4.4 Write unit tests for Sell_Advisor
    - Test exact boundary values (excess = 2.0, excess = 5.0)
    - Test position not full exclusion
    - Test premium_rate == sell_threshold returns None
    - Test sell_amount calculation
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.7_

- [x] 5. Implement Comparison_Engine
  - [x] 5.1 Create `src/comparison_engine.py`
    - Implement `compare_group(group_name, etf_premiums) -> ComparisonResult | None`
    - Filter out entries where premium_rate is None
    - If fewer than 2 valid → return None
    - Sort by premium_rate ascending (stable sort preserves config order for ties)
    - Recommended = first after sort; alternatives = remaining with diff calculated
    - _Requirements: 4.1, 4.2, 4.3, 4.6, 4.7, 4.8_

  - [ ]* 5.2 Write property test for comparison minimum selection
    - **Property 5: Comparison Minimum Selection**
    - **Validates: Requirements 4.1, 4.7**

  - [ ]* 5.3 Write property test for comparison diff non-negativity
    - **Property 6: Comparison Diff Non-Negativity**
    - **Validates: Requirements 4.4**

  - [ ]* 5.4 Write unit tests for Comparison_Engine
    - Test single ETF group returns None
    - Test all-error group returns None
    - Test tie-breaking by config order
    - Test diff calculation correctness
    - _Requirements: 4.1, 4.2, 4.3, 4.6, 4.7_

- [x] 6. Checkpoint - Core components complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Implement Strategy_Engine orchestrator
  - [x] 7.1 Create `src/strategy_engine.py`
    - Implement `StrategyEngine` class with `__init__(config, premium_store)`
    - Implement `get_adjusted_rules(etf_config, premium_rate)`: persist premium, query history, call threshold_calculator, handle StoreError gracefully (fallback to static rules)
    - Implement `get_sell_suggestions(results)`: iterate results, call evaluate_sell for each ETF with valid premium
    - Implement `get_comparisons(results)`: group ETFs by config group field, call compare_group per group
    - Handle Store read/write failures with logging and graceful fallback
    - _Requirements: 1.3, 1.4, 2.1, 3.1, 4.1_

  - [ ]* 7.2 Write unit tests for Strategy_Engine
    - Test adjusted rules returned on successful store interaction
    - Test fallback to static rules on store write failure
    - Test fallback to static rules on store read failure
    - Test sell suggestions aggregation
    - Test comparisons grouping logic
    - _Requirements: 1.3, 1.4, 2.1, 3.1, 4.1_

- [x] 8. Extend Formatter for new message types
  - [x] 8.1 Add sell suggestion formatting to `src/formatter.py`
    - Implement `format_sell_section(suggestions)` for plain text and Telegram MarkdownV2
    - Use ⚠️ emoji prefix with "卖出建议" label
    - Include ETF code, name, current premium rate, and suggested sell percentage
    - Apply MarkdownV2 escaping for Telegram output
    - _Requirements: 3.5, 6.1, 6.4, 6.5_

  - [x] 8.2 Add comparison recommendation formatting to `src/formatter.py`
    - Implement `format_comparison_section(comparisons)` for plain text and Telegram MarkdownV2
    - Use "同类对比" section header
    - Show group name, recommended ETF code/name, premium rate, and diff from alternatives
    - Apply MarkdownV2 escaping for Telegram output
    - _Requirements: 4.4, 6.2, 6.4, 6.5_

  - [x] 8.3 Update main format functions to include new sections
    - Modify `format_plain_text()` and `format_telegram_markdown()` to accept sell suggestions and comparison results
    - Render sections in fixed order: buy suggestions → sell suggestions → group comparison
    - Do not render empty sections when no suggestions/recommendations exist
    - Display both original and adjusted threshold values when thresholds are adjusted
    - Maintain existing buy suggestion format unchanged
    - _Requirements: 2.6, 6.3, 6.5, 6.6_

  - [ ]* 8.4 Write unit tests for Formatter extensions
    - Test sell section rendered with correct emoji and format
    - Test comparison section rendered correctly
    - Test empty sections not rendered
    - Test MarkdownV2 escaping for new sections
    - Test section ordering
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

- [x] 9. Integrate Strategy_Engine into Monitor
  - [x] 9.1 Update `src/monitor.py` to use Strategy_Engine
    - Instantiate `PremiumStore` and `StrategyEngine` in Monitor.__init__()
    - After premium calculation, call `strategy_engine.get_adjusted_rules()` and use adjusted rules for `calculate_suggested_buy()`
    - After all ETFs processed, call `get_sell_suggestions()` and `get_comparisons()`
    - Pass sell suggestions and comparisons to Formatter
    - _Requirements: 1.1, 1.3, 1.4, 2.1, 3.1, 4.1_

  - [ ]* 9.2 Write integration tests for Monitor with Strategy_Engine
    - Test end-to-end Monitor.run() with mocked data sources
    - Verify premium stored after each ETF processed
    - Verify adjusted thresholds used in buy calculation
    - Verify sell suggestions appear when conditions met
    - Verify group comparisons rendered in output
    - Test backward compatibility: old config (no new fields) produces identical behavior
    - _Requirements: 1.1, 2.1, 3.1, 4.1, 5.6_

- [x] 10. Final checkpoint - Full integration verified
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- All new modules follow existing project patterns: errors contained per-ETF, never crash overall monitoring pipeline
- Implementation language: Python 3.11+ with pytest and hypothesis

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "2.1"] },
    { "id": 2, "tasks": ["1.3", "2.2", "2.3", "2.4", "3.1", "4.1", "5.1"] },
    { "id": 3, "tasks": ["3.2", "3.3", "3.4", "3.5", "4.2", "4.3", "4.4", "5.2", "5.3", "5.4"] },
    { "id": 4, "tasks": ["7.1"] },
    { "id": 5, "tasks": ["7.2", "8.1", "8.2"] },
    { "id": 6, "tasks": ["8.3"] },
    { "id": 7, "tasks": ["8.4", "9.1"] },
    { "id": 8, "tasks": ["9.2"] }
  ]
}
```
