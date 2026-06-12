"""Tests for /record and /telegram/webhook endpoints in src/api.py.

Validates Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.10
"""

from unittest.mock import patch, MagicMock

import pytest

from src.api import app
from src.exceptions import StoreError


@pytest.fixture(autouse=True)
def clear_api_secret(monkeypatch):
    """Keep endpoint auth opt-in within tests unless a case sets it."""
    monkeypatch.delenv("ETF_API_SECRET", raising=False)
    monkeypatch.delenv("API_SECRET", raising=False)
    monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET", raising=False)


@pytest.fixture
def client():
    """Flask test client."""
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def mock_config():
    """Mock config with valid ETF codes."""
    config = MagicMock()
    etf1 = MagicMock()
    etf1.code = "513500"
    etf2 = MagicMock()
    etf2.code = "159501"
    config.etfs = [etf1, etf2]
    config.data_dir = "data"
    config.telegram.bot_token = "test-bot-token"
    config.telegram.chat_id = "12345"
    return config


class TestRecordEndpoint:
    """Tests for POST /record endpoint."""

    def test_record_requires_api_secret_when_configured(self, client, monkeypatch):
        """Configured API secret requires X-API-Key or Bearer auth."""
        monkeypatch.setenv("ETF_API_SECRET", "secret")

        response = client.post("/record", json={
            "code": "513500",
            "type": "buy",
            "amount": 5000.0,
        })

        assert response.status_code == 401

    @patch("src.api.PositionStore")
    @patch("src.api.load_config")
    def test_record_buy_success(self, mock_load, mock_store_cls, client, mock_config):
        """Req 8.1: Successful buy recording returns 200 with success message."""
        mock_load.return_value = mock_config
        mock_store = MagicMock()
        mock_store_cls.return_value = mock_store

        response = client.post("/record", json={
            "code": "513500",
            "type": "buy",
            "amount": 5000.0,
        })

        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "success"
        assert "已记录: 513500 买入 5000.0 元" in data["message"]
        mock_store.append.assert_called_once_with("513500", "buy", 5000.0)

    @patch("src.api.PositionStore")
    @patch("src.api.load_config")
    def test_record_sell_success(self, mock_load, mock_store_cls, client, mock_config):
        """Req 8.2: Successful sell recording returns 200 with success message."""
        mock_load.return_value = mock_config
        mock_store = MagicMock()
        mock_store_cls.return_value = mock_store

        response = client.post("/record", json={
            "code": "513500",
            "type": "sell",
            "amount": 3000.0,
        })

        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "success"
        assert "已记录: 513500 卖出 3000.0 元" in data["message"]
        mock_store.append.assert_called_once_with("513500", "sell", 3000.0)

    @patch("src.api.load_config")
    def test_record_invalid_code(self, mock_load, client, mock_config):
        """Req 8.3: Invalid ETF code returns 400."""
        mock_load.return_value = mock_config

        response = client.post("/record", json={
            "code": "999999",
            "type": "buy",
            "amount": 5000.0,
        })

        assert response.status_code == 400
        data = response.get_json()
        assert data["status"] == "error"
        assert "ETF代码 999999 不在配置中" in data["message"]

    @patch("src.api.load_config")
    def test_record_invalid_type(self, mock_load, client, mock_config):
        """Req 8.5: Invalid type returns 400."""
        mock_load.return_value = mock_config

        response = client.post("/record", json={
            "code": "513500",
            "type": "hold",
            "amount": 5000.0,
        })

        assert response.status_code == 400
        data = response.get_json()
        assert data["status"] == "error"
        assert "type 必须为 buy 或 sell" in data["message"]

    @patch("src.api.load_config")
    def test_record_negative_amount(self, mock_load, client, mock_config):
        """Req 8.4: Negative amount returns 400."""
        mock_load.return_value = mock_config

        response = client.post("/record", json={
            "code": "513500",
            "type": "buy",
            "amount": -100,
        })

        assert response.status_code == 400
        data = response.get_json()
        assert data["status"] == "error"
        assert "金额必须为正数且不超过10000000" in data["message"]

    @patch("src.api.load_config")
    def test_record_zero_amount(self, mock_load, client, mock_config):
        """Req 8.4: Zero amount returns 400."""
        mock_load.return_value = mock_config

        response = client.post("/record", json={
            "code": "513500",
            "type": "buy",
            "amount": 0,
        })

        assert response.status_code == 400
        data = response.get_json()
        assert data["status"] == "error"
        assert "金额必须为正数且不超过10000000" in data["message"]

    @patch("src.api.load_config")
    def test_record_amount_exceeds_max(self, mock_load, client, mock_config):
        """Req 8.4: Amount exceeding 10,000,000 returns 400."""
        mock_load.return_value = mock_config

        response = client.post("/record", json={
            "code": "513500",
            "type": "buy",
            "amount": 10_000_001,
        })

        assert response.status_code == 400
        data = response.get_json()
        assert data["status"] == "error"
        assert "金额必须为正数且不超过10000000" in data["message"]

    @patch("src.api.load_config")
    def test_record_amount_at_max_boundary(self, mock_load, client, mock_config):
        """Req 8.4: Amount exactly at 10,000,000 is valid."""
        mock_load.return_value = mock_config

        with patch("src.api.PositionStore") as mock_store_cls:
            mock_store = MagicMock()
            mock_store_cls.return_value = mock_store

            response = client.post("/record", json={
                "code": "513500",
                "type": "buy",
                "amount": 10_000_000,
            })

            assert response.status_code == 200
            data = response.get_json()
            assert data["status"] == "success"

    @patch("src.api.PositionStore")
    @patch("src.api.load_config")
    def test_record_store_error(self, mock_load, mock_store_cls, client, mock_config):
        """Req 8.10: StoreError returns 500 with storage failure message."""
        mock_load.return_value = mock_config
        mock_store = MagicMock()
        mock_store.append.side_effect = StoreError("write", "positions", "disk full")
        mock_store_cls.return_value = mock_store

        response = client.post("/record", json={
            "code": "513500",
            "type": "buy",
            "amount": 5000.0,
        })

        assert response.status_code == 500
        data = response.get_json()
        assert data["status"] == "error"
        assert "存储写入失败" in data["message"]

    def test_record_invalid_json(self, client):
        """Invalid JSON body returns 400."""
        response = client.post("/record", data="not json", content_type="text/plain")

        assert response.status_code == 400


class TestTelegramWebhookEndpoint:
    """Tests for POST /telegram/webhook endpoint."""

    @patch("src.api._send_telegram_reply")
    @patch("src.api.PositionStore")
    @patch("src.api.load_config")
    def test_webhook_buy_success(self, mock_load, mock_store_cls, mock_reply, client, mock_config):
        """Req 8.6: /buy command records transaction and replies with success."""
        mock_load.return_value = mock_config
        mock_store = MagicMock()
        mock_store_cls.return_value = mock_store

        update = {
            "message": {
                "text": "/buy 513500 5000",
                "chat": {"id": 12345},
            }
        }

        response = client.post("/telegram/webhook", json=update)

        assert response.status_code == 200
        mock_store.append.assert_called_once_with("513500", "buy", 5000.0)
        mock_reply.assert_called_once_with(12345, "✅ 已记录: 513500 买入 5000.0 元")

    @patch("src.api._send_telegram_reply")
    @patch("src.api.PositionStore")
    @patch("src.api.load_config")
    def test_webhook_ignores_unauthorized_chat(self, mock_load, mock_store_cls, mock_reply, client, mock_config):
        """Commands from chats other than configured chat_id are ignored."""
        mock_load.return_value = mock_config

        update = {
            "message": {
                "text": "/buy 513500 5000",
                "chat": {"id": 99999},
            }
        }

        response = client.post("/telegram/webhook", json=update)

        assert response.status_code == 200
        mock_store_cls.assert_not_called()
        mock_reply.assert_not_called()

    @patch("src.api._send_telegram_reply")
    @patch("src.api.PositionStore")
    @patch("src.api.load_config")
    def test_webhook_requires_secret_token_when_configured(
        self, mock_load, mock_store_cls, mock_reply, client, mock_config, monkeypatch
    ):
        """Configured Telegram webhook secret must match Telegram header."""
        monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "telegram-secret")
        mock_load.return_value = mock_config

        update = {
            "message": {
                "text": "/buy 513500 5000",
                "chat": {"id": 12345},
            }
        }

        response = client.post("/telegram/webhook", json=update)

        assert response.status_code == 200
        mock_store_cls.assert_not_called()
        mock_reply.assert_not_called()

    @patch("src.api._send_telegram_reply")
    @patch("src.api.PositionStore")
    @patch("src.api.load_config")
    def test_webhook_accepts_matching_secret_token(
        self, mock_load, mock_store_cls, mock_reply, client, mock_config, monkeypatch
    ):
        """Matching Telegram webhook secret allows command processing."""
        monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "telegram-secret")
        mock_load.return_value = mock_config
        mock_store = MagicMock()
        mock_store_cls.return_value = mock_store

        update = {
            "message": {
                "text": "/buy 513500 5000",
                "chat": {"id": 12345},
            }
        }

        response = client.post(
            "/telegram/webhook",
            json=update,
            headers={"X-Telegram-Bot-Api-Secret-Token": "telegram-secret"},
        )

        assert response.status_code == 200
        mock_store.append.assert_called_once_with("513500", "buy", 5000.0)

    @patch("src.api._send_telegram_reply")
    @patch("src.api.PositionStore")
    @patch("src.api.load_config")
    def test_webhook_sell_success(self, mock_load, mock_store_cls, mock_reply, client, mock_config):
        """Req 8.7: /sell command records transaction and replies with success."""
        mock_load.return_value = mock_config
        mock_store = MagicMock()
        mock_store_cls.return_value = mock_store

        update = {
            "message": {
                "text": "/sell 513500 3000",
                "chat": {"id": 12345},
            }
        }

        response = client.post("/telegram/webhook", json=update)

        assert response.status_code == 200
        mock_store.append.assert_called_once_with("513500", "sell", 3000.0)
        mock_reply.assert_called_once_with(12345, "✅ 已记录: 513500 卖出 3000.0 元")

    @patch("src.api._send_telegram_reply")
    @patch("src.api.load_config")
    def test_webhook_invalid_code(self, mock_load, mock_reply, client, mock_config):
        """Req 8.6: Invalid code replies with error."""
        mock_load.return_value = mock_config

        update = {
            "message": {
                "text": "/buy 999999 5000",
                "chat": {"id": 12345},
            }
        }

        response = client.post("/telegram/webhook", json=update)

        assert response.status_code == 200
        mock_reply.assert_called_once()
        reply_text = mock_reply.call_args[0][1]
        assert "ETF代码 999999 不在配置中" in reply_text

    @patch("src.api._send_telegram_reply")
    @patch("src.api.load_config")
    def test_webhook_invalid_amount(self, mock_load, mock_reply, client, mock_config):
        """Req 8.6: Invalid amount replies with error."""
        mock_load.return_value = mock_config

        update = {
            "message": {
                "text": "/buy 513500 abc",
                "chat": {"id": 12345},
            }
        }

        response = client.post("/telegram/webhook", json=update)

        assert response.status_code == 200
        mock_reply.assert_called_once()
        reply_text = mock_reply.call_args[0][1]
        assert "金额必须为正数且不超过10000000" in reply_text

    @patch("src.api._send_telegram_reply")
    @patch("src.api.PositionStore")
    @patch("src.api.load_config")
    def test_webhook_store_error(self, mock_load, mock_store_cls, mock_reply, client, mock_config):
        """Req 8.10: StoreError replies with storage failure message."""
        mock_load.return_value = mock_config
        mock_store = MagicMock()
        mock_store.append.side_effect = StoreError("write", "positions", "disk full")
        mock_store_cls.return_value = mock_store

        update = {
            "message": {
                "text": "/buy 513500 5000",
                "chat": {"id": 12345},
            }
        }

        response = client.post("/telegram/webhook", json=update)

        assert response.status_code == 200
        mock_reply.assert_called_once()
        reply_text = mock_reply.call_args[0][1]
        assert "记录失败" in reply_text

    def test_webhook_non_matching_message(self, client):
        """Non-command messages are silently ignored."""
        update = {
            "message": {
                "text": "Hello world",
                "chat": {"id": 12345},
            }
        }

        response = client.post("/telegram/webhook", json=update)

        assert response.status_code == 200
        data = response.get_json()
        assert data["ok"] is True

    def test_webhook_empty_update(self, client):
        """Empty update is silently ignored."""
        response = client.post("/telegram/webhook", json={})

        assert response.status_code == 200

    def test_webhook_no_message(self, client):
        """Update without message field is silently ignored."""
        update = {"update_id": 123}

        response = client.post("/telegram/webhook", json=update)

        assert response.status_code == 200

    @patch("src.api._send_telegram_reply")
    @patch("src.api.PositionStore")
    @patch("src.api.load_config")
    def test_webhook_decimal_amount(self, mock_load, mock_store_cls, mock_reply, client, mock_config):
        """Decimal amounts are accepted."""
        mock_load.return_value = mock_config
        mock_store = MagicMock()
        mock_store_cls.return_value = mock_store

        update = {
            "message": {
                "text": "/buy 513500 1234.56",
                "chat": {"id": 12345},
            }
        }

        response = client.post("/telegram/webhook", json=update)

        assert response.status_code == 200
        mock_store.append.assert_called_once_with("513500", "buy", 1234.56)


class TestDataRestoreEndpoint:
    """Tests for POST /data/restore endpoint."""

    @patch("src.api.load_config")
    def test_restore_rejects_invalid_premium_key(self, mock_load, client, mock_config, tmp_path):
        """premium_* restore keys must match configured ETF codes."""
        mock_config.data_dir = str(tmp_path)
        mock_load.return_value = mock_config

        response = client.post("/data/restore", json={
            "premium_../../bad": {"records": []},
        })

        assert response.status_code == 400
        data = response.get_json()
        assert data["status"] == "error"
        assert "无效的溢价率数据键" in data["message"]

    @patch("src.api.load_config")
    def test_restore_accepts_configured_premium_key(self, mock_load, client, mock_config, tmp_path):
        """Configured ETF codes can be restored normally."""
        mock_config.data_dir = str(tmp_path)
        mock_load.return_value = mock_config

        response = client.post("/data/restore", json={
            "premium_513500": {"records": []},
        })

        assert response.status_code == 200
        assert (tmp_path / "513500.json").exists()
