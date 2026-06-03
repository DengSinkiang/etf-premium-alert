"""HaoETF data source implementation for QDII ETF Premium Monitor.

Fetches ETF price and IOPV data from the HaoETF website as a fallback
data source when AKShare is unavailable.
"""

import logging
import re
from datetime import datetime

import requests

from src.exceptions import DataFetchError
from src.models import ETFData

logger = logging.getLogger("monitor")

# Request timeout in seconds
_REQUEST_TIMEOUT = 10


class HaoETFSource:
    """HaoETF 数据源，通过解析网页获取 ETF 实时数据。

    Implements the DataSource protocol with a fetch(code) -> ETFData method.
    Used as a fallback when the primary AKShare source fails.
    """

    def fetch(self, code: str) -> ETFData:
        """通过 HaoETF 网页获取 ETF 实时数据。

        Args:
            code: ETF 代码，如 "513500"

        Returns:
            ETFData: 包含价格、IOPV、更新时间和来源的数据对象

        Raises:
            DataFetchError: HTTP 请求失败或页面解析失败时抛出
        """
        url = f"https://www.haoetf.com/etfdetail/{code}.html"

        try:
            response = requests.get(url, timeout=_REQUEST_TIMEOUT, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            response.raise_for_status()
        except requests.Timeout:
            logger.error(f"[HaoETFSource] 获取 {code} 数据超时")
            raise DataFetchError(source="HaoETF", code=code, reason="请求超时")
        except requests.RequestException as e:
            logger.error(f"[HaoETFSource] 获取 {code} 数据失败: {e}")
            raise DataFetchError(source="HaoETF", code=code, reason=str(e))

        html = response.text

        try:
            price = self._extract_price(html)
            iopv = self._extract_iopv(html)
            update_time = self._extract_update_time(html)
        except DataFetchError:
            raise
        except Exception as e:
            logger.error(f"[HaoETFSource] 解析 {code} 页面数据失败: {e}")
            raise DataFetchError(source="HaoETF", code=code, reason=f"页面解析失败: {e}")

        logger.info(f"[HaoETFSource] 获取 {code} 数据成功: price={price}, iopv={iopv}")

        return ETFData(
            code=code,
            price=price,
            iopv=iopv,
            update_time=update_time,
            source="HaoETF",
        )

    def _extract_price(self, html: str) -> float:
        """从 HTML 中提取当前价格。

        Looks for patterns like '当前价' or 'price' followed by a numeric value.

        Args:
            html: 网页 HTML 内容

        Returns:
            当前价格浮点数

        Raises:
            DataFetchError: 无法提取价格时抛出
        """
        # Try common patterns for price extraction
        patterns = [
            r'(?:当前价|现价|最新价)[：:\s]*(\d+\.?\d*)',
            r'"price"\s*[：:]\s*"?(\d+\.?\d*)"?',
            r'price["\s:]+(\d+\.?\d*)',
            r'class="[^"]*price[^"]*"[^>]*>(\d+\.?\d*)',
        ]

        for pattern in patterns:
            match = re.search(pattern, html)
            if match:
                return float(match.group(1))

        raise DataFetchError(source="HaoETF", code="", reason="无法从页面提取当前价格")

    def _extract_iopv(self, html: str) -> float:
        """从 HTML 中提取估算净值(IOPV)。

        Looks for patterns like 'IOPV', '估值', '净值估算' followed by a numeric value.

        Args:
            html: 网页 HTML 内容

        Returns:
            IOPV 浮点数

        Raises:
            DataFetchError: 无法提取 IOPV 时抛出
        """
        patterns = [
            r'(?:IOPV|iopv|估算净值|净值估算|参考净值)[：:\s]*(\d+\.?\d*)',
            r'"iopv"\s*[：:]\s*"?(\d+\.?\d*)"?',
            r'iopv["\s:]+(\d+\.?\d*)',
            r'class="[^"]*iopv[^"]*"[^>]*>(\d+\.?\d*)',
            r'(?:估值|净值)[：:\s]*(\d+\.?\d*)',
        ]

        for pattern in patterns:
            match = re.search(pattern, html)
            if match:
                return float(match.group(1))

        raise DataFetchError(source="HaoETF", code="", reason="无法从页面提取IOPV数据")

    def _extract_update_time(self, html: str) -> datetime:
        """从 HTML 中提取数据更新时间。

        Looks for datetime patterns in the page content.
        Falls back to current time if no timestamp is found.

        Args:
            html: 网页 HTML 内容

        Returns:
            数据更新时间的 datetime 对象
        """
        # Try to find a datetime pattern like "2024-01-15 09:30:01" or "2024/01/15 09:30"
        patterns = [
            r'(\d{4}[-/]\d{2}[-/]\d{2}\s+\d{2}:\d{2}:\d{2})',
            r'(\d{4}[-/]\d{2}[-/]\d{2}\s+\d{2}:\d{2})',
        ]

        for pattern in patterns:
            match = re.search(pattern, html)
            if match:
                time_str = match.group(1)
                # Normalize separator
                time_str = time_str.replace("/", "-")
                try:
                    if len(time_str) == 16:  # YYYY-MM-DD HH:MM
                        return datetime.strptime(time_str, "%Y-%m-%d %H:%M")
                    else:  # YYYY-MM-DD HH:MM:SS
                        return datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    continue

        # Fallback to current time if no valid timestamp found
        logger.warning("[HaoETFSource] 无法从页面提取更新时间，使用当前时间")
        return datetime.now()
