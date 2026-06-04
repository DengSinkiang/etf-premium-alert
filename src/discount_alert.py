"""Discount alert detection for ETF premium monitor."""

import threading

from src.models import AppConfig, DiscountAlertResult


class DiscountAlert:
    """折价提醒检测器。

    检测 ETF 是否触发折价买入提醒条件，并通过内部去重保证
    同一运行周期内每个 ETF 最多产生一条提醒。

    Thread Safety:
        _alerted_codes is protected by a threading.Lock since check() may be
        called concurrently from multiple ETF processing threads.
    """

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._alerted_codes: set[str] = set()
        self._lock = threading.Lock()

    def check(
        self,
        code: str,
        name: str,
        premium_rate: float | None,
        price: float,
        iopv: float,
        discount_threshold: float,
    ) -> DiscountAlertResult | None:
        """检查是否触发折价提醒。

        Args:
            code: ETF 代码
            name: ETF 名称
            premium_rate: 当前溢价率（负值表示折价），None 时跳过
            price: 当前价格
            iopv: 当前 IOPV
            discount_threshold: 折价触发阈值（百分比）

        Returns:
            DiscountAlertResult 若触发提醒，否则 None
        """
        # premium_rate 为 None 时跳过检查
        if premium_rate is None:
            return None

        # Lock protects _alerted_codes which may be accessed by concurrent threads
        with self._lock:
            # 已在本周期内提醒过的 ETF 不再重复提醒
            if code in self._alerted_codes:
                return None

            # 触发条件：溢价率为负 且 绝对值 >= 阈值
            if premium_rate < 0 and abs(premium_rate) >= discount_threshold:
                self._alerted_codes.add(code)
                return DiscountAlertResult(
                    code=code,
                    name=name,
                    discount_rate=abs(premium_rate),
                    price=price,
                    iopv=iopv,
                )

        return None

    def reset(self) -> None:
        """重置已提醒记录（新监控周期开始时调用）。"""
        self._alerted_codes.clear()
