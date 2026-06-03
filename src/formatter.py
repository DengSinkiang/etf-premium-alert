"""Output formatters for the QDII ETF Premium Monitor."""

from datetime import datetime
from typing import Optional

from src.models import MonitorResult, DiscountAlertResult, DailySummaryReport


def _format_update_time(update_time: Optional[datetime]) -> str:
    """Format update time for display."""
    if update_time is None:
        return "N/A"
    return update_time.strftime("%Y-%m-%d %H:%M:%S")


def format_volume_info_plain(volume: float | None, turnover_rate: float | None) -> str:
    """格式化成交量/换手率纯文本。

    成交量以万手为单位保留 2 位小数，换手率保留 2 位小数加 %。
    None 时显示 N/A。

    Args:
        volume: 成交量（手），可为 None
        turnover_rate: 换手率（%），可为 None

    Returns:
        格式化后的纯文本字符串
    """
    if volume is None:
        vol_str = "N/A"
    else:
        vol_str = f"{volume / 10000:.2f} 万手"

    if turnover_rate is None:
        rate_str = "N/A"
    else:
        rate_str = f"{turnover_rate:.2f}%"

    return f"成交量: {vol_str} | 换手率: {rate_str}"


def _format_volume_info_telegram(volume: float | None, turnover_rate: float | None) -> str:
    """格式化成交量/换手率 Telegram MarkdownV2。

    Args:
        volume: 成交量（手），可为 None
        turnover_rate: 换手率（%），可为 None

    Returns:
        Telegram MarkdownV2 格式的字符串
    """
    if volume is None:
        vol_str = "N/A"
    else:
        vol_str = _escape_telegram_markdown(f"{volume / 10000:.2f} 万手")

    if turnover_rate is None:
        rate_str = "N/A"
    else:
        rate_str = _escape_telegram_markdown(f"{turnover_rate:.2f}%")

    return f"`成交量:` {vol_str} \\| `换手率:` {rate_str}"


def format_plain_text(results: list[MonitorResult]) -> str:
    """生成命令行纯文本输出。

    Args:
        results: MonitorResult 列表

    Returns:
        格式化后的纯文本字符串
    """
    lines: list[str] = []

    # Header with timestamp
    header_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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
            lines.append(f"  当前溢价率:   {result.premium_rate}%")
            lines.append(f"  目标仓位:     {result.target_amount} 元")
            lines.append(f"  已买金额:     {result.bought_amount} 元")
            lines.append(f"  剩余目标:     {result.remaining_target} 元")
            lines.append(f"  建议买入区间: {result.suggested_buy_min} ~ {result.suggested_buy_max} 元")
            lines.append(f"  操作建议:     {result.suggestion}")
            lines.append(f"  数据来源:     {result.source}")
            lines.append(f"  更新时间:     {_format_update_time(result.update_time)}")
            # 成交量/换手率展示（仅高溢价时有值）
            if result.volume is not None or result.turnover_rate is not None:
                lines.append(f"  {format_volume_info_plain(result.volume, result.turnover_rate)}")
            lines.append("")

    return "\n".join(lines)


def _escape_telegram_markdown(text: str) -> str:
    """Escape special characters for Telegram MarkdownV2.

    Telegram MarkdownV2 requires escaping: _ * [ ] ( ) ~ ` > # + - = | { } . !
    """
    special_chars = r"_*[]()~`>#+-=|{}.!"
    escaped = ""
    for char in text:
        if char in special_chars:
            escaped += f"\\{char}"
        else:
            escaped += char
    return escaped


def format_telegram_markdown(results: list[MonitorResult]) -> str:
    """生成 Telegram MarkdownV2 格式消息。

    Args:
        results: MonitorResult 列表

    Returns:
        Telegram MarkdownV2 格式的字符串
    """
    lines: list[str] = []

    # Header with timestamp
    header_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines.append(f"*QDII ETF 溢价率监控*")
    lines.append(f"`{_escape_telegram_markdown(header_time)}`")
    lines.append("")

    for i, result in enumerate(results):
        if i > 0:
            lines.append("\\-\\-\\-")
            lines.append("")

        if result.error is not None:
            # Error case
            escaped_code = _escape_telegram_markdown(result.code)
            escaped_name = _escape_telegram_markdown(result.name)
            escaped_error = _escape_telegram_markdown(result.error)
            lines.append(f"*\\[{escaped_code}\\] {escaped_name}*")
            lines.append(f"❌ 错误: {escaped_error}")
            lines.append("")
        else:
            # Normal case with all fields
            escaped_code = _escape_telegram_markdown(result.code)
            escaped_name = _escape_telegram_markdown(result.name)
            lines.append(f"*\\[{escaped_code}\\] {escaped_name}*")
            lines.append(f"`当前价格:` {_escape_telegram_markdown(str(result.price))}")
            lines.append(f"`估算净值:` {_escape_telegram_markdown(str(result.iopv))}")
            lines.append(f"`当前溢价率:` {_escape_telegram_markdown(str(result.premium_rate))}%")
            lines.append(f"`目标仓位:` {_escape_telegram_markdown(str(result.target_amount))} 元")
            lines.append(f"`已买金额:` {_escape_telegram_markdown(str(result.bought_amount))} 元")
            lines.append(f"`剩余目标:` {_escape_telegram_markdown(str(result.remaining_target))} 元")
            lines.append(
                f"`建议买入:` {_escape_telegram_markdown(str(result.suggested_buy_min))} "
                f"\\~ {_escape_telegram_markdown(str(result.suggested_buy_max))} 元"
            )
            lines.append(f"`操作建议:` {_escape_telegram_markdown(str(result.suggestion))}")
            lines.append(f"`数据来源:` {_escape_telegram_markdown(str(result.source))}")
            lines.append(f"`更新时间:` {_escape_telegram_markdown(_format_update_time(result.update_time))}")
            # 成交量/换手率展示（仅高溢价时有值）
            if result.volume is not None or result.turnover_rate is not None:
                lines.append(_format_volume_info_telegram(result.volume, result.turnover_rate))
            lines.append("")

    return "\n".join(lines)


def format_discount_alert_plain(alert: DiscountAlertResult) -> str:
    """格式化折价提醒纯文本。

    Args:
        alert: DiscountAlertResult 折价提醒结果

    Returns:
        格式化后的纯文本字符串
    """
    lines: list[str] = []
    lines.append("💰 折价买入提醒")
    lines.append("")
    lines.append(f"[{alert.code}] {alert.name}")
    lines.append(f"  当前折价率:   {alert.discount_rate:.2f}%")
    lines.append(f"  当前价格:     {alert.price}")
    lines.append(f"  IOPV:         {alert.iopv}")
    return "\n".join(lines)


def format_discount_alert_telegram(alert: DiscountAlertResult) -> str:
    """格式化折价提醒 Telegram MarkdownV2 消息。

    Args:
        alert: DiscountAlertResult 折价提醒结果

    Returns:
        Telegram MarkdownV2 格式的字符串
    """
    escaped_code = _escape_telegram_markdown(alert.code)
    escaped_name = _escape_telegram_markdown(alert.name)
    escaped_rate = _escape_telegram_markdown(f"{alert.discount_rate:.2f}%")
    escaped_price = _escape_telegram_markdown(str(alert.price))
    escaped_iopv = _escape_telegram_markdown(str(alert.iopv))

    lines: list[str] = []
    lines.append("💰 *折价买入提醒*")
    lines.append("")
    lines.append(f"*\\[{escaped_code}\\] {escaped_name}*")
    lines.append(f"`当前折价率:` {escaped_rate}")
    lines.append(f"`当前价格:` {escaped_price}")
    lines.append(f"`IOPV:` {escaped_iopv}")
    return "\n".join(lines)


def format_daily_summary_plain(report: DailySummaryReport) -> str:
    """格式化每日摘要纯文本。

    Args:
        report: DailySummaryReport 每日摘要报告

    Returns:
        格式化后的纯文本字符串
    """
    lines: list[str] = []

    lines.append(f"=== 每日摘要报告 ({report.date}) ===")
    lines.append("")

    for i, summary in enumerate(report.summaries):
        if i > 0:
            lines.append("---")
            lines.append("")

        lines.append(f"[{summary.code}] {summary.name}")

        if summary.status == "no_data":
            lines.append("  当日无数据")
            lines.append("")
        elif summary.status == "read_error":
            lines.append("  数据读取失败")
            lines.append("")
        else:
            lines.append(f"  最高溢价率:   {summary.max_premium:.2f}%")
            lines.append(f"  最低溢价率:   {summary.min_premium:.2f}%")
            lines.append(f"  收盘溢价率:   {summary.close_premium:.2f}%")
            buy_icon = "✅" if summary.buy_triggered else "❌"
            sell_icon = "✅" if summary.sell_triggered else "❌"
            lines.append(f"  买入触发:     {buy_icon}")
            lines.append(f"  卖出触发:     {sell_icon}")
            lines.append("")

    return "\n".join(lines)


def format_daily_summary_telegram(report: DailySummaryReport) -> str:
    """格式化每日摘要 Telegram MarkdownV2 消息。

    Args:
        report: DailySummaryReport 每日摘要报告

    Returns:
        Telegram MarkdownV2 格式的字符串
    """
    lines: list[str] = []

    escaped_date = _escape_telegram_markdown(report.date)
    lines.append("📊 *每日摘要报告*")
    lines.append(f"`{escaped_date}`")
    lines.append("")

    for i, summary in enumerate(report.summaries):
        if i > 0:
            lines.append("\\-\\-\\-")
            lines.append("")

        escaped_code = _escape_telegram_markdown(summary.code)
        escaped_name = _escape_telegram_markdown(summary.name)
        lines.append(f"*\\[{escaped_code}\\] {escaped_name}*")

        if summary.status == "no_data":
            lines.append("⚠️ 当日无数据")
            lines.append("")
        elif summary.status == "read_error":
            lines.append("❌ 数据读取失败")
            lines.append("")
        else:
            escaped_max = _escape_telegram_markdown(f"{summary.max_premium:.2f}%")
            escaped_min = _escape_telegram_markdown(f"{summary.min_premium:.2f}%")
            escaped_close = _escape_telegram_markdown(f"{summary.close_premium:.2f}%")
            buy_icon = "✅" if summary.buy_triggered else "❌"
            sell_icon = "✅" if summary.sell_triggered else "❌"
            lines.append(f"`最高溢价率:` {escaped_max}")
            lines.append(f"`最低溢价率:` {escaped_min}")
            lines.append(f"`收盘溢价率:` {escaped_close}")
            lines.append(f"`买入触发:` {buy_icon}")
            lines.append(f"`卖出触发:` {sell_icon}")
            lines.append("")

    return "\n".join(lines)
