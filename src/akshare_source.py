"""AKShare data source for ETF real-time data retrieval."""

import logging
from datetime import datetime

import akshare as ak
import pandas as pd

from src.exceptions import DataFetchError
from src.models import ETFData

logger = logging.getLogger("monitor")


class AKShareSource:
    """通过 AKShare 库获取 ETF 实时数据。

    使用东方财富 ETF 实时行情接口 (fund_etf_spot_em) 获取
    ETF 当前价格和 IOPV 实时估值。

    支持 DataFrame 缓存：每个监控周期内，fund_etf_spot_em() 仅调用一次，
    后续 fetch() 调用直接从缓存中查找 ETF 数据。
    """

    def __init__(self) -> None:
        self._df_cache: pd.DataFrame | None = None

    def fetch(self, code: str) -> ETFData:
        """获取指定 ETF 的实时数据。

        On first call per cycle, calls fund_etf_spot_em() and caches result.
        Subsequent calls look up from cache without network I/O.

        Args:
            code: ETF 代码，如 "513500"

        Returns:
            ETFData: 包含价格、IOPV、更新时间和来源的数据对象

        Raises:
            DataFetchError: 网络超时、连接失败或数据解析错误时抛出
        """
        # Populate cache if empty
        if self._df_cache is None:
            try:
                self._df_cache = ak.fund_etf_spot_em()
            except TimeoutError as e:
                logger.error(f"获取 {code} 数据超时: {e}")
                raise DataFetchError(source="AKShare", code=code, reason=f"请求超时: {e}")
            except ConnectionError as e:
                logger.error(f"获取 {code} 数据连接失败: {e}")
                raise DataFetchError(source="AKShare", code=code, reason=f"连接失败: {e}")
            except Exception as e:
                logger.error(f"获取 ETF 数据失败: {e}")
                raise DataFetchError(source="AKShare", code=code, reason=str(e))

        # Look up ETF code from cached DataFrame
        df = self._df_cache
        row = df[df["代码"] == code]
        if row.empty:
            logger.error(f"未找到 ETF 代码 {code} 的数据")
            raise DataFetchError(
                source="AKShare", code=code, reason=f"未找到 ETF 代码 {code}"
            )

        record = row.iloc[0]

        # 提取价格（检测停牌：最新价为空且换手率为0）
        price = record.get("最新价")
        turnover = record.get("换手率")
        is_suspended = (price is None or pd.isna(price)) and (turnover is not None and turnover == 0)

        if is_suspended:
            logger.warning(f"ETF {code} 疑似停牌（最新价为空且换手率为0）")
            raise DataFetchError(
                source="AKShare", code=code, reason="该ETF今日停牌，无实时交易数据"
            )

        if price is None or pd.isna(price):
            price = record.get("昨收")
            if price is not None and not pd.isna(price):
                logger.warning(f"ETF {code} 最新价为空，使用昨收价 {price}")
            else:
                logger.error(f"ETF {code} 最新价和昨收价均无效")
                raise DataFetchError(
                    source="AKShare", code=code, reason="最新价数据无效"
                )

        # 提取 IOPV
        iopv = record.get("IOPV实时估值")
        if iopv is None or pd.isna(iopv):
            logger.error(f"ETF {code} IOPV 数据无效")
            raise DataFetchError(
                source="AKShare", code=code, reason="IOPV 数据无效"
            )

        # 提取更新时间
        update_time = record.get("更新时间")
        if update_time is None or pd.isna(update_time):
            update_time_dt = datetime.now()
        elif isinstance(update_time, pd.Timestamp):
            update_time_dt = update_time.to_pydatetime().replace(tzinfo=None)
        elif isinstance(update_time, datetime):
            update_time_dt = update_time.replace(tzinfo=None)
        else:
            try:
                update_time_dt = pd.Timestamp(update_time).to_pydatetime().replace(tzinfo=None)
            except (ValueError, TypeError):
                update_time_dt = datetime.now()

        etf_data = ETFData(
            code=code,
            price=float(price),
            iopv=float(iopv),
            update_time=update_time_dt,
            source="AKShare",
        )

        logger.info(
            f"获取 {code} 数据成功: 价格={etf_data.price}, "
            f"IOPV={etf_data.iopv}, 更新时间={etf_data.update_time}"
        )
        return etf_data

    def invalidate_cache(self) -> None:
        """Clear the cached DataFrame, forcing next fetch to call the API."""
        self._df_cache = None
