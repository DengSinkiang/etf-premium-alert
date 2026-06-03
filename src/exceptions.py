"""Custom exception classes for the QDII ETF Premium Monitor."""


class DataFetchError(Exception):
    """数据获取失败"""

    def __init__(self, source: str, code: str, reason: str):
        self.source = source
        self.code = code
        self.reason = reason
        super().__init__(f"[{source}] 获取 {code} 数据失败: {reason}")


class ConfigError(Exception):
    """配置加载失败，包含所有缺失字段"""

    def __init__(self, missing_fields: list[str]):
        self.missing_fields = missing_fields
        super().__init__(f"缺少必填字段: {', '.join(missing_fields)}")


class StoreError(Exception):
    """存储操作失败"""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)
