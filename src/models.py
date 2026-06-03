"""Core data models for the QDII ETF Premium Monitor."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class ETFData:
    """数据源返回的 ETF 原始数据"""

    code: str
    price: float
    iopv: float
    update_time: datetime
    source: str  # "AKShare" | "HaoETF"


@dataclass
class PremiumRule:
    """溢价率买入规则"""

    max_premium: float  # 溢价率上限百分比
    min_ratio: float  # 剩余目标金额的最小买入比例 (0.0-1.0)
    max_ratio: float  # 剩余目标金额的最大买入比例 (0.0-1.0)


@dataclass
class ETFConfig:
    """单只 ETF 的配置"""

    code: str  # ETF 代码，如 "513500"
    name: str  # ETF 名称，如 "博时标普500ETF"
    target_amount: float  # 目标仓位金额
    bought_amount: float  # 已买金额
    premium_rules: list[PremiumRule]  # 溢价率买入规则


@dataclass
class TelegramConfig:
    """Telegram 推送配置"""

    enabled: bool
    bot_token: Optional[str]
    chat_id: Optional[str]


@dataclass
class AppConfig:
    """应用程序完整配置"""

    etfs: list[ETFConfig]
    telegram: TelegramConfig
    alert_threshold: float  # 提醒阈值


@dataclass
class MonitorResult:
    """单只 ETF 的完整监控结果"""

    code: str
    name: str
    price: Optional[float]
    iopv: Optional[float]
    premium_rate: Optional[float]
    target_amount: float
    bought_amount: float
    remaining_target: float
    suggested_buy_min: Optional[int]
    suggested_buy_max: Optional[int]
    suggestion: Optional[str]
    source: Optional[str]
    update_time: Optional[datetime]
    error: Optional[str]  # 失败时的错误信息
