"""Data source protocol and manager for ETF data retrieval."""

import logging
from typing import Protocol

from src.exceptions import DataFetchError
from src.models import ETFData

logger = logging.getLogger("monitor")


class DataSource(Protocol):
    """Abstract interface for ETF data sources.

    Implementations must provide a fetch method that retrieves
    ETF data for a given code, raising DataFetchError on failure.
    """

    def fetch(self, code: str) -> ETFData:
        """获取 ETF 数据，失败时抛出 DataFetchError。

        Args:
            code: ETF 代码，如 "513500"

        Returns:
            ETFData: 包含价格、净值、更新时间和来源的数据对象

        Raises:
            DataFetchError: 数据获取失败时抛出
        """
        ...


class DataSourceManager:
    """管理数据源的主备切换策略。

    使用 Primary-Fallback 模式：优先使用主数据源（AKShare），
    主源失败时自动切换到备用数据源（HaoETF）。
    两者均失败时记录错误日志并返回 None，不抛出异常。
    """

    def __init__(self, primary: DataSource, fallback: DataSource) -> None:
        """初始化数据源管理器。

        Args:
            primary: 主数据源（AKShare）
            fallback: 备用数据源（HaoETF）
        """
        self._primary = primary
        self._fallback = fallback

    def get_etf_data(self, code: str) -> tuple[ETFData | None, str | None]:
        """尝试主数据源，失败则切换备用，均失败返回 (None, error_reason)。

        数据来源标记 source 仅在成功获取数据时设置：
        - AKShare 成功 → source="AKShare"（由 AKShareSource 标记）
        - AKShare 失败、HaoETF 成功 → source="HaoETF"（由 HaoETFSource 标记）
        - 均失败 → 返回 (None, 错误原因)

        Args:
            code: ETF 代码，如 "513500"

        Returns:
            (ETFData, None) 成功时，或 (None, 错误原因字符串) 均失败时
        """
        primary_reason = ""

        # 尝试主数据源
        try:
            data = self._primary.fetch(code)
            return data, None
        except DataFetchError as e:
            primary_reason = e.reason
            logger.warning(
                f"[DataSourceManager] 主数据源获取 {code} 失败: {e.reason}，尝试备用数据源"
            )
        except Exception as e:
            primary_reason = str(e)
            logger.warning(
                f"[DataSourceManager] 主数据源获取 {code} 发生未预期错误: {e}，尝试备用数据源"
            )

        # 尝试备用数据源
        try:
            data = self._fallback.fetch(code)
            return data, None
        except DataFetchError as e:
            logger.error(
                f"[DataSourceManager] 备用数据源获取 {code} 失败: {e.reason}"
            )
        except Exception as e:
            logger.error(
                f"[DataSourceManager] 备用数据源获取 {code} 发生未预期错误: {e}"
            )

        # 两个数据源均失败
        logger.error(
            f"[DataSourceManager] 所有数据源获取 {code} 均失败，返回 None"
        )
        return None, primary_reason
