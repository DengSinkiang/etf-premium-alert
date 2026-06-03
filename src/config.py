"""Configuration loader for the QDII ETF Premium Monitor."""

import os
import sys
from typing import Any

import yaml

from src.exceptions import ConfigError
from src.models import AppConfig, ETFConfig, PremiumRule, TelegramConfig


def load_config(path: str = "config.yaml") -> AppConfig:
    """加载并验证配置。

    优先从环境变量 ETF_CONFIG_YAML 读取配置内容（适用于 Render 等云部署），
    如果环境变量未设置，则从文件路径加载。

    验证所有必填字段，若有缺失则在单条错误信息中报告全部缺失字段名称，
    然后以 sys.exit(1) 终止程序。

    Args:
        path: 配置文件路径，默认为 "config.yaml"

    Returns:
        AppConfig 对象

    Raises:
        SystemExit: 配置无效时退出
    """
    # 1. 尝试从环境变量或文件加载 YAML
    config_yaml_env = os.environ.get("ETF_CONFIG_YAML")

    if config_yaml_env:
        # 从环境变量加载
        try:
            raw: Any = yaml.safe_load(config_yaml_env)
        except yaml.YAMLError as e:
            print(f"环境变量 ETF_CONFIG_YAML 格式错误: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        # 从文件加载
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = yaml.safe_load(f)
        except FileNotFoundError:
            print(f"配置文件 {path} 未找到", file=sys.stderr)
            sys.exit(1)
        except yaml.YAMLError as e:
            print(f"配置文件格式错误: {e}", file=sys.stderr)
            sys.exit(1)

    if not isinstance(raw, dict):
        print("配置文件格式错误: 期望 YAML 字典格式", file=sys.stderr)
        sys.exit(1)

    # 2. 验证所有必填字段，收集全部缺失项
    missing_fields: list[str] = []

    if "etfs" not in raw or not raw["etfs"]:
        missing_fields.append("etfs")

    if "alert_threshold" not in raw:
        missing_fields.append("alert_threshold")

    # 验证每个 ETF 条目的必填字段
    etfs_raw = raw.get("etfs", [])
    if isinstance(etfs_raw, list):
        for i, etf in enumerate(etfs_raw):
            if not isinstance(etf, dict):
                missing_fields.append(f"etfs[{i}]")
                continue
            if "code" not in etf:
                missing_fields.append(f"etfs[{i}].code")
            if "name" not in etf:
                missing_fields.append(f"etfs[{i}].name")
            if "target_amount" not in etf:
                missing_fields.append(f"etfs[{i}].target_amount")

    # 如果有缺失字段，报告并退出
    if missing_fields:
        error = ConfigError(missing_fields)
        print(str(error), file=sys.stderr)
        sys.exit(1)

    # 3. 转换为 AppConfig 数据结构
    etfs: list[ETFConfig] = []
    for etf_raw in etfs_raw:
        premium_rules: list[PremiumRule] = []
        for rule_raw in etf_raw.get("premium_rules", []):
            premium_rules.append(
                PremiumRule(
                    max_premium=float(rule_raw["max_premium"]),
                    min_ratio=float(rule_raw["min_ratio"]),
                    max_ratio=float(rule_raw["max_ratio"]),
                )
            )

        etfs.append(
            ETFConfig(
                code=str(etf_raw["code"]),
                name=str(etf_raw["name"]),
                target_amount=float(etf_raw["target_amount"]),
                bought_amount=float(etf_raw.get("bought_amount", 0.0)),
                premium_rules=premium_rules,
            )
        )

    # Telegram 配置（可选，默认 disabled）
    telegram_raw = raw.get("telegram", {})
    if not isinstance(telegram_raw, dict):
        telegram_raw = {}

    telegram = TelegramConfig(
        enabled=bool(telegram_raw.get("enabled", False)),
        bot_token=telegram_raw.get("bot_token"),
        chat_id=telegram_raw.get("chat_id"),
    )

    alert_threshold = float(raw["alert_threshold"])

    return AppConfig(
        etfs=etfs,
        telegram=telegram,
        alert_threshold=alert_threshold,
    )
