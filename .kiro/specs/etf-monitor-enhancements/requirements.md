# Requirements Document

## Introduction

本需求文档描述 ETF 溢价监控系统的四项功能增强：折价提醒、成交量/换手率监控、每日摘要报告和交易日历感知。这些增强将提升系统的买入时机判断能力、提供收盘后的回顾视角，并避免在非交易日发起无效请求。

## Glossary

- **Monitor**: ETF 溢价监控系统的核心编排模块，负责协调数据获取、计算和通知流程
- **Premium_Rate**: 溢价率，计算公式为 (价格 - IOPV) / IOPV * 100，正值为溢价，负值为折价
- **Discount_Rate**: 折价率，即溢价率为负值时的绝对值
- **AKShare_Source**: 通过 AKShare 库获取 ETF 实时行情数据的数据源模块
- **Volume**: 成交量，指 ETF 当日的累计成交股数
- **Turnover_Rate**: 换手率，指当日成交量占流通份额的百分比
- **Notifier**: Telegram 消息推送模块，负责将监控结果发送给用户
- **Daily_Summary_Reporter**: 每日摘要报告生成模块，收盘后汇总当日监控数据
- **Trading_Calendar**: 交易日历模块，判断当前日期是否为 A 股交易日
- **Premium_Store**: 溢价率历史数据存储模块，以 JSON 文件形式持久化每次监控记录
- **Strategy_Engine**: 策略引擎，聚合卖出建议、同类对比和动态阈值调整等策略输出

## Requirements

### Requirement 1: 折价提醒

**User Story:** As a 投资者, I want 在 ETF 出现折价时收到买入提醒, so that 我能抓住折价带来的低价买入机会。

#### Acceptance Criteria

1. WHEN Premium_Rate 为负值且其绝对值大于或等于该 ETF 配置的 discount_threshold, THE Monitor SHALL 生成折价买入提醒
2. WHEN 折价买入提醒生成时, THE Monitor SHALL 在提醒中包含以下信息：ETF 代码、ETF 名称、当前折价率（百分比，保留两位小数）、当前价格和 IOPV
3. WHEN 折价买入提醒生成时, THE Notifier SHALL 通过 Telegram 推送折价提醒消息给用户
4. IF Telegram 推送失败（网络超时或 API 返回非 200 状态码）, THEN THE Notifier SHALL 记录错误日志并返回失败状态，不中断监控流程
5. THE AppConfig SHALL 支持为每只 ETF 单独配置 discount_threshold 字段，取值范围为 0.1 到 20.0（百分比），默认值为 1.0
6. WHEN Premium_Rate 为负值且绝对值小于 discount_threshold, THE Monitor SHALL 不生成折价提醒
7. WHEN 某只 ETF 已在当次监控周期内生成过折价提醒, THE Monitor SHALL 不对该 ETF 重复生成折价提醒

### Requirement 2: 成交量与换手率监控

**User Story:** As a 投资者, I want 在溢价较高时查看成交量和换手率数据, so that 我能判断是否有套利资金流入从而做出更准确的交易决策。

#### Acceptance Criteria

1. THE AKShare_Source SHALL 从行情数据中提取成交量（Volume）和换手率（Turnover_Rate）字段并包含在返回的数据对象中，成交量单位为手，换手率单位为百分比
2. IF Premium_Rate 大于或等于 alert_threshold, THEN THE Monitor SHALL 在监控结果中附带当前成交量和换手率数据
3. THE Formatter SHALL 在纯文本输出和 Telegram 消息中以统一格式展示成交量和换手率：成交量以万手为单位保留 2 位小数（如 "123.45 万手"），换手率保留 2 位小数并附加百分号（如 "1.23%"）
4. IF AKShare 返回的成交量或换手率字段为空、NaN 或为负数, THEN THE AKShare_Source SHALL 将对应字段设为 None 并记录警告日志，不中断主流程
5. IF 成交量或换手率字段值为 None, THEN THE Formatter SHALL 在对应展示位置显示 "N/A"
6. IF Premium_Rate 小于 alert_threshold, THEN THE Monitor SHALL 不在监控结果中附带成交量和换手率数据

### Requirement 3: 每日摘要报告

**User Story:** As a 投资者, I want 在每个交易日收盘后收到一份当日汇总报告, so that 我能回顾当天所有 ETF 的溢价表现和操作建议。

#### Acceptance Criteria

1. WHEN 北京时间到达 AppConfig 中配置的 summary_time 且当日为交易日时, THE Daily_Summary_Reporter SHALL 生成当日摘要报告
2. THE Daily_Summary_Reporter SHALL 在摘要报告中包含以下内容：每只 ETF 当日最高溢价率、最低溢价率、当日最后一条记录的溢价率（作为收盘溢价率）、当日是否触发过买入建议（基于 Premium_Rate 满足 premium_rules 的记录）、当日是否触发过卖出建议（基于 Premium_Rate 超过 sell_threshold 的记录）
3. THE Daily_Summary_Reporter SHALL 从 Premium_Store 中读取当日（北京时间 00:00:00 至 23:59:59）所有历史溢价率记录用于计算最高和最低值
4. WHEN Premium_Store 中当日无任何记录, THE Daily_Summary_Reporter SHALL 在报告中标注该 ETF 为"当日无数据"，并跳过该 ETF 的溢价率统计
5. WHEN 摘要报告生成完毕, THE Notifier SHALL 通过 Telegram 推送摘要报告消息给用户
6. IF Telegram 推送摘要报告失败, THEN THE Notifier SHALL 记录错误日志包含失败原因，不重试推送
7. IF Premium_Store 读取当日记录时发生异常, THEN THE Daily_Summary_Reporter SHALL 在报告中标注该 ETF 为"数据读取失败"，继续处理其余 ETF，不中断报告生成
8. THE AppConfig SHALL 支持配置 summary_time 字段指定摘要报告触发时间，格式为 "HH:MM"（24小时制北京时间），有效范围为 "00:00" 至 "23:59"，默认值为 "15:30"

### Requirement 4: 交易日历感知

**User Story:** As a 系统运维者, I want 系统自动跳过非交易日的监控请求, so that 不在周末和法定节假日发起无意义的数据请求。

#### Acceptance Criteria

1. WHEN Monitor 启动且当前日期为 A 股非交易日（含周末、法定节假日，排除周末调休工作日）, THE Monitor SHALL 跳过监控流程，记录 INFO 级别日志说明跳过原因（周末或具体节假日名称），并以退出码 0 退出
2. THE Trading_Calendar SHALL 通过 chinese_calendar 库或等效数据源判断指定日期是否为 A 股交易日，覆盖周末调休为工作日的特殊情况
3. IF Trading_Calendar 依赖的外部库导入失败或调用时抛出异常, THEN THE Trading_Calendar SHALL 回退到仅排除周六和周日的基础逻辑，并记录 WARNING 级别日志说明回退原因
4. WHERE 用户通过命令行参数 --force 强制运行, THE Monitor SHALL 跳过交易日判断并执行完整监控流程，无论当前日期是否为交易日
5. THE Trading_Calendar SHALL 提供 is_trading_day(date) 方法，接受日期参数并返回布尔值（True 表示交易日，False 表示非交易日）
6. WHEN Monitor 启动且当前日期为 A 股交易日, THE Monitor SHALL 正常执行完整监控流程，不记录任何交易日判断相关的警告或跳过日志
