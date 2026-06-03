"""Output formatters for the QDII ETF Premium Monitor."""

from datetime import datetime
from typing import Optional

from src.models import MonitorResult


def _format_update_time(update_time: Optional[datetime]) -> str:
    """Format update time for display."""
    if update_time is None:
        return "N/A"
    return update_time.strftime("%Y-%m-%d %H:%M:%S")


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
            lines.append("")

    return "\n".join(lines)
