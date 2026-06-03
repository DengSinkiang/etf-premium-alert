"""Telegram notification module for QDII ETF Premium Monitor."""

import logging
from typing import Optional

import requests

from src.models import TelegramConfig

logger = logging.getLogger("monitor")


class TelegramNotifier:
    """Sends messages via Telegram Bot API.

    Respects the enabled flag in config — when disabled, send() is a no-op
    that returns True. On failure, logs the error and returns False without
    raising exceptions.
    """

    def __init__(self, config: TelegramConfig) -> None:
        self._config = config

    def send(self, message: str) -> bool:
        """Send a message to the configured Telegram chat.

        Args:
            message: The text content to send (MarkdownV2 formatted).

        Returns:
            True if the message was sent successfully or sending was skipped
            (disabled). False if an error occurred.
        """
        if not self._config.enabled:
            return True

        if not self._config.bot_token:
            logger.error("Telegram bot_token 未配置")
            return False

        if not self._config.chat_id:
            logger.error("Telegram chat_id 未配置")
            return False

        url = f"https://api.telegram.org/bot{self._config.bot_token}/sendMessage"
        payload = {
            "chat_id": self._config.chat_id,
            "text": message,
            "parse_mode": "MarkdownV2",
        }

        try:
            response = requests.post(url, json=payload, timeout=30)
            if response.status_code == 200:
                return True
            logger.error(
                "Telegram 推送失败: HTTP %d - %s",
                response.status_code,
                response.text,
            )
            return False
        except requests.RequestException as exc:
            logger.error("Telegram 推送异常: %s", exc)
            return False
