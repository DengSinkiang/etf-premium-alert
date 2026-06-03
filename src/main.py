"""CLI entry point for the QDII ETF Premium Monitor.

Usage:
    python -m src.main [--once] [--config CONFIG_PATH] [--force] [--summary]

Options:
    --once      Execute one monitoring cycle and exit (default behavior, highest priority)
    --config    Path to configuration YAML file (default: config.yaml)
    --force     Force run, skip trading day check
    --summary   Generate and send daily summary report, then exit
"""

import argparse
import logging
import sys

from src.config import load_config
from src.logger import setup_logging
from src.monitor import Monitor

logger = logging.getLogger("monitor")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """解析命令行参数。

    --once 参数优先级最高，始终执行一次监控后退出，无论其他配置如何。

    Args:
        argv: 命令行参数列表，默认使用 sys.argv[1:]

    Returns:
        解析后的参数命名空间
    """
    parser = argparse.ArgumentParser(
        description="QDII ETF 溢价率监控工具",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        default=True,
        help="执行一次监控后退出（默认行为，优先级最高）",
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config.yaml",
        help="配置文件路径（默认: config.yaml）",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="强制运行，跳过交易日判断",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        default=False,
        help="生成并推送每日摘要报告后退出",
    )
    return parser.parse_args(argv)


def _run_summary(config) -> int:
    """生成并推送每日摘要报告。

    1. 实例化 PremiumStore 和 DailySummaryReporter
    2. 调用 generate() 生成 DailySummaryReport
    3. 通过 TelegramNotifier 推送 Telegram 消息（如已启用）
    4. 打印纯文本到 stdout
    5. 退出

    Args:
        config: AppConfig 配置对象

    Returns:
        退出码，0 表示成功
    """
    from src.daily_summary import DailySummaryReporter
    from src.formatter import format_daily_summary_plain, format_daily_summary_telegram
    from src.notifier import TelegramNotifier
    from src.premium_store import PremiumStore

    # Instantiate dependencies
    premium_store = PremiumStore(data_dir=config.data_dir)
    reporter = DailySummaryReporter(config=config, premium_store=premium_store)

    # Generate the daily summary report
    report = reporter.generate()

    # Print plain text to stdout
    plain_text = format_daily_summary_plain(report)
    print(plain_text)

    # Push via Telegram if enabled
    if config.telegram.enabled:
        notifier = TelegramNotifier(config.telegram)
        telegram_message = format_daily_summary_telegram(report)
        success = notifier.send(telegram_message)
        if not success:
            logger.error("每日摘要 Telegram 推送失败")

    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI 主入口函数。

    Args:
        argv: 命令行参数列表，默认使用 sys.argv[1:]

    Returns:
        退出码，0 表示成功
    """
    args = parse_args(argv)

    # Set up logging (errors go to stderr via logging console handler)
    setup_logging()

    # Load configuration (exits with sys.exit(1) on failure)
    config = load_config(args.config)

    # --summary: generate and send daily summary, then exit
    if args.summary:
        return _run_summary(config)

    # --once has highest priority: always run once and exit
    monitor = Monitor(config)
    monitor.run()

    return 0


if __name__ == "__main__":
    sys.exit(main())
