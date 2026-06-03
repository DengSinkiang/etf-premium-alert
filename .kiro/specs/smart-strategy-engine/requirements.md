# Requirements Document

## Introduction

The Smart Strategy Engine extends the QDII ETF Premium Monitor with three intelligent capabilities: dynamic threshold adjustment based on historical premium data, sell suggestions when positions are fully built and premiums are excessive, and multi-ETF comparison within the same index group to recommend the lowest-premium option. These features require adding a data persistence layer (for historical tracking), new configuration fields, and new message formatting.

## Glossary

- **Strategy_Engine**: The core module that coordinates dynamic threshold calculation, sell signal generation, and multi-ETF comparison logic
- **Premium_Store**: The persistence layer responsible for storing and retrieving historical premium rate records for each ETF
- **Threshold_Calculator**: The component that computes adjusted buy thresholds based on recent historical premium averages
- **Sell_Advisor**: The component that evaluates whether a fully-built position should be reduced based on current premium conditions
- **Comparison_Engine**: The component that groups ETFs by index and compares their premium rates to identify the lowest-premium option
- **ETF_Group**: A named collection of ETFs tracking the same underlying index (e.g., multiple S&P 500 ETFs)
- **Lookback_Window**: The configurable number of days used to calculate the historical average premium rate (default: 7 days)
- **Sell_Threshold**: The premium rate percentage above which the Sell_Advisor recommends reducing a fully-built position
- **Adjusted_Threshold**: A premium rule threshold that has been shifted based on the historical average premium rate
- **Formatter**: The module responsible for rendering monitoring results, sell alerts, and comparison recommendations into human-readable text

## Requirements

### Requirement 1: Historical Premium Data Persistence

**User Story:** As a system operator, I want historical premium rates stored persistently, so that the system can calculate rolling averages for dynamic threshold adjustments.

#### Acceptance Criteria

1. WHEN a premium rate is successfully calculated for an ETF, THE Premium_Store SHALL persist the ETF code, premium rate value (as a decimal number), and timestamp (recorded to the second in local system time) as a new record
2. WHEN historical records are requested for an ETF, THE Premium_Store SHALL return all records with timestamps within the Lookback_Window number of days prior to the current time (inclusive of boundary), ordered by timestamp ascending
3. IF the Premium_Store encounters a write failure, THEN THE Strategy_Engine SHALL log the error and continue processing using static thresholds from config
4. IF the Premium_Store encounters a read failure, THEN THE Threshold_Calculator SHALL fall back to using the static premium_rules from configuration without adjustment
5. THE Premium_Store SHALL use a file-based JSON storage format compatible with the Render deployment environment (no external database dependency)
6. WHEN a write operation occurs, THE Premium_Store SHALL remove all records with timestamps more than 30 days before the current system time to prevent unbounded storage growth
7. WHEN a premium rate is persisted for an ETF that already has a record with the same timestamp (to the second), THE Premium_Store SHALL overwrite the existing record rather than creating a duplicate

### Requirement 2: Dynamic Threshold Adjustment

**User Story:** As an investor, I want buy thresholds to adapt to recent market premiums, so that my buy decisions account for sustained high or low premium environments.

#### Acceptance Criteria

1. WHEN the Threshold_Calculator computes adjusted thresholds, THE Threshold_Calculator SHALL retrieve all premium rate records within the configured Lookback_Window for that ETF and calculate the arithmetic mean of those values
2. WHEN the historical average premium is strictly above the baseline (first rule's max_premium after sorting by max_premium ascending), THE Threshold_Calculator SHALL shift each premium rule's max_premium upward by the difference between the historical average and the baseline, rounded to two decimal places
3. WHEN the historical average premium is at or below the baseline, THE Threshold_Calculator SHALL use the original static premium_rules without adjustment
4. IF fewer than 3 historical records exist for an ETF within the Lookback_Window, THEN THE Threshold_Calculator SHALL use the original static premium_rules without adjustment
5. THE Threshold_Calculator SHALL cap the maximum upward shift at 5.0 percentage points; if the calculated shift exceeds 5.0, the shift applied SHALL be 5.0
6. WHEN adjusted thresholds are applied, THE Formatter SHALL display both the original and adjusted threshold values in the monitoring output
7. WHEN thresholds are adjusted, THE Threshold_Calculator SHALL not modify the min_ratio or max_ratio values of any rule; only the max_premium boundary values SHALL be shifted

### Requirement 3: Sell Suggestion Generation

**User Story:** As an investor, I want the system to suggest reducing my position when premiums are excessively high and my position is fully built, so that I can lock in gains from overpriced shares.

#### Acceptance Criteria

1. WHEN an ETF's bought_amount is greater than or equal to target_amount AND the current premium rate is strictly greater than the configured Sell_Threshold, THE Sell_Advisor SHALL generate a sell suggestion for that ETF
2. WHEN a sell suggestion is generated, THE Sell_Advisor SHALL calculate the suggested sell amount as a percentage of the ETF's bought_amount, selecting the midpoint of the tier range corresponding to how far the premium exceeds the Sell_Threshold
3. THE Sell_Advisor SHALL define three sell tiers based on how many percentage points the premium exceeds Sell_Threshold: greater than 0 up to 2 percentage points (suggest selling 15% of bought_amount), greater than 2 up to 5 percentage points (suggest selling 30% of bought_amount), and greater than 5 percentage points (suggest selling 50% of bought_amount)
4. IF the ETF's bought_amount is less than target_amount, THEN THE Sell_Advisor SHALL not generate any sell suggestion regardless of premium rate
5. WHEN a sell suggestion is generated, THE Formatter SHALL render the sell alert in a dedicated section with a warning emoji (⚠️) prefix and the label "卖出建议", visually separated from the buy suggestions section
6. THE configuration SHALL include a sell_threshold field per ETF with a default value of 8.0 percent
7. IF the current premium rate is exactly equal to the Sell_Threshold AND bought_amount is greater than or equal to target_amount, THEN THE Sell_Advisor SHALL not generate a sell suggestion

### Requirement 4: Multi-ETF Comparison and Recommendation

**User Story:** As an investor, I want to compare premium rates across ETFs tracking the same index, so that I can buy the one with the lowest premium for cost efficiency.

#### Acceptance Criteria

1. WHEN 2 or more ETFs belong to the same ETF_Group and have valid premium data, THE Comparison_Engine SHALL compare their current premium rates and identify the ETF with the lowest premium rate
2. WHEN a comparison is performed, THE Comparison_Engine SHALL only include ETFs for which premium data was successfully retrieved (exclude errored ETFs)
3. IF all ETFs in a group have errors, THEN THE Comparison_Engine SHALL skip the comparison for that group and report no recommendation
4. WHEN a lowest-premium ETF is identified, THE Formatter SHALL display a recommendation indicating the ETF name and code, its premium rate, and the premium rate difference between it and each other ETF in the group
5. THE configuration SHALL support an optional "group" field per ETF that specifies the ETF_Group name as a non-empty string (e.g., "sp500", "nasdaq100")
6. WHEN an ETF_Group contains only one ETF with valid data, THE Comparison_Engine SHALL skip the comparison for that group (no recommendation needed for single-ETF groups)
7. IF 2 or more ETFs in a group share the same lowest premium rate, THEN THE Comparison_Engine SHALL select the first one in configuration order as the recommended ETF
8. IF an ETF does not have a "group" field configured, THEN THE Comparison_Engine SHALL exclude that ETF from all group comparisons

### Requirement 5: Configuration Schema Extension

**User Story:** As a system operator, I want the configuration to support new strategy fields, so that I can control thresholds, grouping, and sell parameters without code changes.

#### Acceptance Criteria

1. THE configuration loader SHALL accept an optional "lookback_days" field at the top level as a positive integer between 1 and 90 inclusive, with a default value of 7
2. THE configuration loader SHALL accept an optional "sell_threshold" field per ETF as a numeric value between 0.1 and 50.0 inclusive, with a default value of 8.0
3. THE configuration loader SHALL accept an optional "group" field per ETF as a non-empty string identifier with a maximum length of 64 characters
4. THE configuration loader SHALL accept an optional "data_dir" field at the top level specifying the directory for Premium_Store data files, defaulting to "data"
5. IF a provided optional field has an invalid type or value outside its valid range (e.g., non-numeric sell_threshold, lookback_days of 0, or group as a non-string type), THEN THE configuration loader SHALL print a validation error message to stderr identifying the invalid field and exit with code 1
6. THE configuration loader SHALL maintain backward compatibility with existing config.yaml files that lack the new optional fields by applying the specified default values
7. IF a "group" field is present but is an empty string, THEN THE configuration loader SHALL treat that ETF as ungrouped (equivalent to the field being absent)

### Requirement 6: Formatter Enhancement for New Message Types

**User Story:** As an investor, I want monitoring notifications to clearly present sell alerts and comparison recommendations alongside buy suggestions, so that I have a complete view of actionable insights.

#### Acceptance Criteria

1. WHEN sell suggestions exist in the monitoring results, THE Formatter SHALL render a dedicated "卖出建议" (Sell Suggestions) section with a ⚠️ emoji prefix, listing each sell suggestion with the ETF code, ETF name, current premium rate, and the suggested sell percentage range
2. WHEN comparison recommendations exist, THE Formatter SHALL render a dedicated "同类对比" (Group Comparison) section listing each group's name, the recommended ETF code and name, its premium rate, and the premium rate difference from the next-highest ETF in the group
3. THE Formatter SHALL maintain the existing buy suggestion format unchanged for backward compatibility
4. WHEN rendering for Telegram, THE Formatter SHALL apply MarkdownV2 escaping to all new message sections using the same escaping rules as existing sections
5. WHEN no sell suggestions and no comparison recommendations exist, THE Formatter SHALL not render empty sections
6. THE Formatter SHALL render sections in the following fixed order: buy suggestions first, then sell suggestions, then group comparison
