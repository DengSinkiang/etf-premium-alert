"""CLI entry point for the QDII ETF Premium Monitor.

Usage:
    python -m src.main [--once] [--config CONFIG_PATH]

Options:
    --once      Execute one monitoring cycle and exit (default behavior, highest priority)
    --config    Path to configuration YAML file (default: config.yaml)
"""

import argparse
import sys

from src.config import load_config
from src.logger import setup_logging
from src.monitor import Monitor


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
    return parser.parse_args(argv)


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

    # --once has highest priority: always run once and exit
    monitor = Monitor(config)
    monitor.run()

    return 0


if __name__ == "__main__":
    sys.exit(main())
