# Implementation Plan: ETF Monitor Enhancements

## Overview

本实现计划将 ETF 溢价监控系统的四项功能增强（折价提醒、成交量/换手率监控、每日摘要报告、交易日历感知）分解为可逐步执行的编码任务。每个任务构建在前一任务基础上，确保无孤立代码。使用 Python 实现，基于现有项目结构和风格。

## Tasks

- [x] 1. 扩展数据模型和配置
  - [x] 1.1 扩展 `src/models.py` 添加新数据类和字段
    - 在 `ETFData` 中添加 `volume: float | None = None` 和 `turnover_rate: float | None = None` 字段
    - 在 `MonitorResult` 中添加 `volume: float | None = None` 和 `turnover_rate: float | None = None` 字段
    - 在 `ETFConfig` 中添加 `discount_threshold: float = 1.0` 字段
    - 在 `AppConfig` 中添加 `summary_time: str = "15:30"` 字段
    - 新增 `DiscountAlertResult` 数据类（code, name, discount_rate, price, iopv）
    - 新增 `ETFDailySummary` 数据类（code, name, max_premium, min_premium, close_premium, buy_triggered, sell_triggered, status）
    - 新增 `DailySummaryReport` 数据类（date, summaries）
    - _Requirements: 1.5, 2.1, 3.2, 3.8_

  - [x] 1.2 扩展 `src/config.py` 支持新配置字段解析和验证
    - 解析每个 ETF 的 `discount_threshold` 字段，默认值 1.0，验证范围 [0.1, 20.0]
    - 解析顶层 `summary_time` 字段，默认值 "15:30"，验证 HH:MM 格式且在 00:00-23:59 范围内
    - 添加对应的验证错误消息输出
    - _Requirements: 1.5, 3.8_

  - [ ]* 1.3 编写属性测试：discount_threshold 配置验证
    - **Property 8: discount_threshold 配置验证**
    - **Validates: Requirements 1.5**
    - 生成随机 float 值，验证 [0.1, 20.0] 范围内通过验证，范围外导致失败

- [x] 2. 实现交易日历模块
  - [x] 2.1 创建 `src/trading_calendar.py` 实现 TradingCalendar 类
    - 实现 `is_trading_day(date)` 方法，优先使用 `chinese_calendar.is_workday()` 判断
    - 实现 `_fallback_check(date)` 回退逻辑：仅排除周六和周日
    - 当 `chinese_calendar` 导入失败或调用异常时，回退到基础逻辑并记录 WARNING 日志
    - 默认参数为 None 时使用当前北京时间日期
    - _Requirements: 4.1, 4.2, 4.3, 4.5, 4.6_

  - [ ]* 2.2 编写属性测试：交易日历回退正确性
    - **Property 7: 交易日历回退正确性**
    - **Validates: Requirements 4.3**
    - 生成随机日期（2020-2030 范围），验证回退逻辑中 weekday 0-4 返回 True，5-6 返回 False

  - [x] 2.3 扩展 `src/main.py` 添加 `--force` CLI 参数和交易日判断逻辑
    - 添加 `--force` 命令行参数
    - 在 Monitor.run() 前检查 TradingCalendar，非交易日且无 --force 时记录 INFO 日志并以 exit(0) 退出
    - _Requirements: 4.1, 4.4_

  - [ ]* 2.4 编写单元测试：交易日历和 --force 参数
    - 测试 is_trading_day 返回正确结果（工作日/周末）
    - 测试 chinese_calendar 不可用时的回退逻辑
    - 测试 --force 参数跳过交易日判断
    - _Requirements: 4.1, 4.3, 4.4_

- [x] 3. Checkpoint - 确保所有测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. 实现折价提醒模块
  - [x] 4.1 创建 `src/discount_alert.py` 实现 DiscountAlert 类
    - 实现 `check(code, name, premium_rate, price, iopv, discount_threshold)` 方法
    - 触发条件：`premium_rate < 0` 且 `abs(premium_rate) >= discount_threshold`
    - 通过 `_alerted_codes: set[str]` 实现同一运行周期内每个 ETF 最多提醒一次
    - 实现 `reset()` 方法清除已提醒记录
    - premium_rate 为 None 时跳过检查返回 None
    - _Requirements: 1.1, 1.6, 1.7_

  - [ ]* 4.2 编写属性测试：折价提醒条件正确性
    - **Property 1: 折价提醒条件正确性**
    - **Validates: Requirements 1.1, 1.6**
    - 生成随机 (premium_rate [-20, 20], discount_threshold [0.1, 20.0]) 对，验证 alert 生成 iff 条件满足

  - [ ]* 4.3 编写属性测试：折价提醒去重（幂等性）
    - **Property 3: 折价提醒去重（幂等性）**
    - **Validates: Requirements 1.7**
    - 生成随机调用序列（1-10 次相同 code），验证最多产生 1 个 alert

  - [x] 4.4 扩展 `src/monitor.py` 集成折价检测逻辑
    - 在 Monitor.__init__ 中实例化 DiscountAlert
    - 在 _process_etf 中计算溢价率后调用 DiscountAlert.check()
    - 触发折价提醒时通过 Notifier 推送 Telegram 消息
    - _Requirements: 1.1, 1.3, 1.4_

  - [ ]* 4.5 编写单元测试：折价提醒集成流程
    - 使用 mock 数据源验证折价时正确生成提醒并推送
    - 验证 Telegram 推送失败时不中断监控
    - _Requirements: 1.3, 1.4_

- [x] 5. 实现成交量与换手率监控
  - [x] 5.1 扩展 `src/akshare_source.py` 提取成交量和换手率字段
    - 从 DataFrame 中提取 "成交量" 和 "换手率" 字段填入 ETFData
    - 字段为空、NaN 或负数时设为 None 并记录 WARNING 日志
    - 不影响主流程返回
    - _Requirements: 2.1, 2.4_

  - [x] 5.2 扩展 `src/monitor.py` 实现成交量条件展示逻辑
    - 当 premium_rate >= alert_threshold 时，将 volume 和 turnover_rate 附加到 MonitorResult
    - 当 premium_rate < alert_threshold 时，MonitorResult 中 volume 和 turnover_rate 保持 None
    - _Requirements: 2.2, 2.6_

  - [ ]* 5.3 编写属性测试：成交量数据条件包含
    - **Property 4: 成交量数据条件包含**
    - **Validates: Requirements 2.2, 2.6**
    - 生成随机 (premium_rate, alert_threshold) 对，验证 volume 有值 iff premium_rate >= threshold

  - [ ]* 5.4 编写单元测试：AKShareSource 成交量/换手率提取
    - 测试正常值提取
    - 测试 NaN/空/负数时设为 None
    - _Requirements: 2.1, 2.4_

- [x] 6. 扩展 Formatter 模块
  - [x] 6.1 在 `src/formatter.py` 中添加折价提醒格式化方法
    - 实现 `format_discount_alert_plain(alert)` 纯文本格式化
    - 实现 `format_discount_alert_telegram(alert)` Telegram MarkdownV2 格式化
    - 输出包含：ETF 代码、名称、折价率（2位小数）、当前价格、IOPV
    - _Requirements: 1.2_

  - [ ]* 6.2 编写属性测试：折价提醒内容完整性
    - **Property 2: 折价提醒内容完整性**
    - **Validates: Requirements 1.2**
    - 生成随机 DiscountAlertResult，验证格式化输出包含所有五项信息

  - [x] 6.3 在 `src/formatter.py` 中添加成交量/换手率格式化方法
    - 实现 `format_volume_info_plain(volume, turnover_rate)` 方法
    - 成交量以万手为单位保留 2 位小数，换手率保留 2 位小数加 %
    - None 时显示 "N/A"
    - 在现有 format_plain_text 和 format_telegram_markdown 中集成成交量展示
    - _Requirements: 2.3, 2.5_

  - [ ]* 6.4 编写属性测试：成交量/换手率格式化正确性
    - **Property 5: 成交量/换手率格式化正确性**
    - **Validates: Requirements 2.3, 2.5**
    - 生成随机 volume（正浮点数）和 turnover_rate（正浮点数），验证输出格式正确；None 时输出 "N/A"

  - [x] 6.5 在 `src/formatter.py` 中添加每日摘要格式化方法
    - 实现 `format_daily_summary_plain(report)` 纯文本格式化
    - 实现 `format_daily_summary_telegram(report)` Telegram MarkdownV2 格式化
    - 包含每只 ETF 的最高/最低/收盘溢价率、买入/卖出触发情况
    - _Requirements: 3.2, 3.5_

- [x] 7. Checkpoint - 确保所有测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. 实现每日摘要报告模块
  - [x] 8.1 创建 `src/daily_summary.py` 实现 DailySummaryReporter 类
    - 实现 `generate(target_date)` 方法，从 PremiumStore 读取当日记录生成摘要
    - 实现 `_get_daily_records(code, target_date)` 按日期筛选记录（北京时间 00:00-23:59）
    - 实现 `_check_buy_triggered(records, etf_config)` 判断是否满足 premium_rules 买入条件
    - 实现 `_check_sell_triggered(records, etf_config)` 判断是否超过 sell_threshold
    - 无记录时标注 status = "no_data"，读取异常时标注 status = "read_error"
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.7_

  - [ ]* 8.2 编写属性测试：每日摘要聚合正确性
    - **Property 6: 每日摘要聚合正确性**
    - **Validates: Requirements 3.2**
    - 生成随机 PremiumRecord 列表（1-50 条），验证 max/min/close 计算正确、buy/sell 触发判断正确

  - [x] 8.3 在 `src/main.py` 中集成每日摘要定时触发逻辑
    - 使用 APScheduler 在 summary_time 触发 DailySummaryReporter.generate()
    - 生成摘要后通过 Notifier 推送 Telegram 消息
    - 推送失败时记录错误日志，不重试
    - _Requirements: 3.1, 3.5, 3.6_

  - [ ]* 8.4 编写单元测试：每日摘要报告生成
    - 测试正常数据的 max/min/close 计算
    - 测试空数据时 status = "no_data"
    - 测试 PremiumStore 异常时 status = "read_error"
    - _Requirements: 3.2, 3.4, 3.7_

- [x] 9. 集成与整体连接
  - [x] 9.1 更新 `config.yaml.example` 添加新配置字段示例
    - 添加 `summary_time` 顶层字段
    - 添加每个 ETF 的 `discount_threshold` 字段
    - _Requirements: 1.5, 3.8_

  - [x] 9.2 更新 `requirements.txt` 添加新依赖
    - 添加 `chinese_calendar` 依赖
    - 添加 `APScheduler` 依赖（如尚未存在）
    - _Requirements: 4.2, 3.1_

  - [ ]* 9.3 编写集成测试：端到端 Monitor 流程验证
    - 使用 mock 数据源测试折价提醒生成与推送
    - 测试高溢价时成交量/换手率出现在输出中
    - 测试 --force 参数跳过交易日判断
    - _Requirements: 1.1, 2.2, 4.4_

- [x] 10. Final checkpoint - 确保所有测试通过
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- 标记 `*` 的子任务为可选测试任务，可以跳过以加快 MVP 进度
- 每个任务引用了具体的需求条款以确保可追溯性
- Checkpoint 任务确保增量验证
- 属性测试验证设计文档中定义的正确性属性
- 单元测试验证具体示例和边界情况
- 项目使用 Python + pytest + hypothesis 进行测试
- 属性测试文件位于 `tests/properties/` 目录

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["1.3", "2.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "4.1"] },
    { "id": 3, "tasks": ["2.4", "4.2", "4.3", "5.1"] },
    { "id": 4, "tasks": ["4.4", "5.2", "6.1"] },
    { "id": 5, "tasks": ["4.5", "5.3", "5.4", "6.2", "6.3"] },
    { "id": 6, "tasks": ["6.4", "6.5", "8.1"] },
    { "id": 7, "tasks": ["8.2", "8.3", "9.1", "9.2"] },
    { "id": 8, "tasks": ["8.4", "9.3"] }
  ]
}
```
