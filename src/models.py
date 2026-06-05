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
    volume: float | None = None  # 成交量（手）
    turnover_rate: float | None = None  # 换手率（%）


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
    sell_threshold: float = 8.0  # 卖出触发溢价率阈值 %
    group: str | None = None  # 分组标识符，用于同类对比
    discount_threshold: float = 1.0  # 折价触发阈值 %，0.1-20.0


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
    lookback_days: int = 7  # 滚动窗口天数，用于计算历史平均溢价率
    data_dir: str = "data"  # Premium_Store 数据目录
    summary_time: str = "15:30"  # 摘要报告触发时间 HH:MM


@dataclass
class TrendInfo:
    """Premium rate trend information."""

    arrow: str  # "↑" | "↓" | "→"
    delta: float  # Signed percentage point change (e.g., +0.50, -0.30)
    previous_rate: float  # The previous premium rate used for comparison


@dataclass
class Transaction:
    """Position tracking transaction record."""

    code: str  # ETF code
    type: str  # "buy" | "sell"
    amount: float  # Yuan amount, rounded to 2 decimal places
    timestamp: str  # ISO 8601 with second precision, e.g. "2024-01-15T10:30:00"


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
    volume: float | None = None  # 成交量（手），仅高溢价时有值
    turnover_rate: float | None = None  # 换手率（%），仅高溢价时有值
    trend_info: TrendInfo | None = None  # 溢价率趋势信息


@dataclass
class PremiumRecord:
    """单条历史溢价率记录"""

    code: str  # ETF 代码
    premium_rate: float  # 溢价率百分比，如 2.35
    timestamp: datetime  # 本地系统时间，精确到秒


@dataclass
class SellSuggestion:
    """生成的卖出建议"""

    code: str  # ETF 代码
    name: str  # ETF 名称
    premium_rate: float  # 当前溢价率 %
    sell_percentage: float  # 建议卖出比例，如 0.15, 0.30, 0.50
    sell_amount: float  # 建议卖出金额 = bought_amount * sell_percentage


@dataclass
class ComparisonResult:
    """单个 ETF 分组的对比推荐结果"""

    group_name: str  # 分组名称，如 "sp500"
    recommended_code: str  # 推荐 ETF 代码
    recommended_name: str  # 推荐 ETF 名称
    recommended_premium: float  # 推荐 ETF 的溢价率
    alternatives: list[dict]  # [{code, name, premium_rate, diff}]


@dataclass
class StrategyResult:
    """单次监控运行的聚合策略输出"""

    sell_suggestions: list[SellSuggestion]
    comparisons: list[ComparisonResult]
    adjusted_rules_map: dict[str, list[PremiumRule]]  # code -> 调整后的规则列表


@dataclass
class DiscountAlertResult:
    """折价提醒结果"""

    code: str  # ETF 代码
    name: str  # ETF 名称
    discount_rate: float  # 折价率（正数百分比，如 1.50）
    price: float  # 当前价格
    iopv: float  # 当前 IOPV


@dataclass
class ETFDailySummary:
    """单只 ETF 的每日摘要"""

    code: str
    name: str
    max_premium: float | None  # 当日最高溢价率
    min_premium: float | None  # 当日最低溢价率
    close_premium: float | None  # 收盘溢价率（当日最后一条记录）
    buy_triggered: bool  # 是否触发过买入建议
    sell_triggered: bool  # 是否触发过卖出建议
    status: str  # "normal" | "no_data" | "read_error"
    open_premium: float | None = None  # 开盘溢价率（当日第一条记录）
    trend_path: str | None = None  # 日内走势路径，如 "低→高→低" 或 "持续上升"


@dataclass
class DailySummaryReport:
    """每日摘要报告"""

    date: str  # 报告日期 YYYY-MM-DD
    summaries: list[ETFDailySummary]
