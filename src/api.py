"""HTTP API for the QDII ETF Premium Monitor.

Provides a Flask-based HTTP interface for triggering the monitoring workflow
via Cloudflare Worker or other HTTP clients.
"""

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import requests as http_requests
from flask import Flask, jsonify, request

from src.config import load_config
from src.exceptions import StoreError
from src.models import MonitorResult
from src.monitor import Monitor
from src.position_store import PositionStore
from src.trading_calendar import TradingCalendar

logger = logging.getLogger("monitor")

app = Flask(__name__)


def _serialize_result(result: MonitorResult) -> dict[str, Any]:
    """Serialize a MonitorResult dataclass to a JSON-compatible dict.

    Converts datetime fields to ISO format strings and preserves None values.

    Args:
        result: A MonitorResult instance to serialize.

    Returns:
        Dictionary with all MonitorResult fields, JSON-serializable.
    """
    update_time: str | None = None
    if result.update_time is not None:
        update_time = result.update_time.isoformat()

    return {
        "code": result.code,
        "name": result.name,
        "price": result.price,
        "iopv": result.iopv,
        "premium_rate": result.premium_rate,
        "target_amount": result.target_amount,
        "bought_amount": result.bought_amount,
        "remaining_target": result.remaining_target,
        "suggested_buy_min": result.suggested_buy_min,
        "suggested_buy_max": result.suggested_buy_max,
        "suggestion": result.suggestion,
        "source": result.source,
        "update_time": update_time,
        "error": result.error,
    }


@app.route("/health", methods=["GET"])
def health() -> tuple[Any, int]:
    """Health check endpoint.

    Returns:
        JSON response with status "ok" and HTTP 200.
    """
    return jsonify({"status": "ok"}), 200


@app.route("/trigger", methods=["GET"])
def trigger() -> tuple[Any, int]:
    """Trigger the full monitoring workflow and return JSON results.

    Loads configuration, runs the monitor, and returns all ETF results
    as a JSON array. Per-ETF errors are included in each result's "error" field.

    Returns HTTP 200 for successful API calls (even if individual ETFs have errors).
    Returns HTTP 500 only for unhandled exceptions (config load failure, service crash).

    Returns:
        Tuple of (JSON response, HTTP status code).
    """
    force = request.args.get("force", "").lower() == "true"
    if not force:
        try:
            calendar = TradingCalendar()
            if not calendar.is_trading_day():
                return jsonify({"status": "skipped", "reason": "non-trading day"}), 200
        except Exception as e:
            logger.warning("交易日历检查失败: %s，继续执行", e)

    try:
        config = load_config()
        monitor = Monitor(config, quiet_mode=False)
        results: list[MonitorResult] = monitor.run()

        serialized = [_serialize_result(r) for r in results]
        return jsonify({"status": "success", "results": serialized}), 200

    except SystemExit:
        # load_config calls sys.exit(1) on failure; catch it for HTTP context
        logger.error("配置加载失败，无法执行监控流程")
        return jsonify({"status": "error", "message": "配置加载失败"}), 500

    except Exception as e:
        logger.error("触发监控流程时发生未处理异常: %s", e)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/summary", methods=["GET"])
def summary() -> tuple[Any, int]:
    """Trigger the daily summary report generation and push.

    Returns:
        Tuple of (JSON response, HTTP status code).
    """
    try:
        config = load_config()

        from src.daily_summary import DailySummaryReporter
        from src.formatter import format_daily_summary_plain, format_daily_summary_telegram
        from src.notifier import TelegramNotifier
        from src.premium_store import PremiumStore

        premium_store = PremiumStore(data_dir=config.data_dir)
        reporter = DailySummaryReporter(config=config, premium_store=premium_store)
        report = reporter.generate()

        # Push via Telegram
        if config.telegram.enabled:
            notifier = TelegramNotifier(config.telegram)
            message = format_daily_summary_telegram(report)
            notifier.send(message)

        plain = format_daily_summary_plain(report)
        return jsonify({"status": "success", "summary": plain}), 200

    except SystemExit:
        logger.error("配置加载失败")
        return jsonify({"status": "error", "message": "配置加载失败"}), 500

    except Exception as e:
        logger.error("生成每日摘要时发生异常: %s", e)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/data/backup", methods=["GET"])
def data_backup() -> tuple[Any, int]:
    """Return all data files as a JSON payload for KV persistence.

    Response format:
    {
        "positions": <contents of positions.json or null>,
        "premium_513500": <contents of 513500.json or null>,
        ...
    }

    Returns HTTP 200 with the backup payload. Files that cannot be read
    are represented as null.
    """
    try:
        config = load_config()
    except SystemExit:
        return jsonify({"status": "error", "message": "配置加载失败"}), 500

    data_dir = Path(config.data_dir)
    payload: dict[str, Any] = {}

    # Read positions.json
    positions_path = data_dir / "positions.json"
    try:
        with open(positions_path, "r", encoding="utf-8") as f:
            payload["positions"] = json.load(f)
    except (IOError, OSError, json.JSONDecodeError):
        payload["positions"] = None

    # Read each ETF premium file
    for etf in config.etfs:
        key = f"premium_{etf.code}"
        file_path = data_dir / f"{etf.code}.json"
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                payload[key] = json.load(f)
        except (IOError, OSError, json.JSONDecodeError):
            payload[key] = None

    return jsonify(payload), 200


@app.route("/data/restore", methods=["POST"])
def data_restore() -> tuple[Any, int]:
    """Accept KV data and write to local files.

    Request body:
    {
        "positions": <JSON object or null>,
        "premium_513500": <JSON object or null>,
        ...
    }

    Writes non-null values to corresponding files using atomic writes.
    Returns 200 {"status": "success"} on completion.
    Returns 400 if the request body is not valid JSON.
    """
    data = request.get_json(force=True, silent=True)
    if data is None or not isinstance(data, dict):
        return jsonify({"status": "error", "message": "请求体必须为有效JSON"}), 400

    try:
        config = load_config()
    except SystemExit:
        return jsonify({"status": "error", "message": "配置加载失败"}), 500

    data_dir = Path(config.data_dir)
    os.makedirs(data_dir, exist_ok=True)

    # Write positions.json if non-null
    positions_value = data.get("positions")
    if positions_value is not None:
        _atomic_write_json(data_dir / "positions.json", positions_value)

    # Write premium_{code}.json files if non-null
    for key, value in data.items():
        if key.startswith("premium_") and value is not None:
            code = key[len("premium_"):]
            _atomic_write_json(data_dir / f"{code}.json", value)

    return jsonify({"status": "success"}), 200


def _atomic_write_json(file_path: Path, content: Any) -> None:
    """Write JSON content to a file atomically using temp file + os.replace.

    Args:
        file_path: Target file path.
        content: JSON-serializable content to write.
    """
    temp_path = file_path.with_suffix(".json.tmp")
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(content, f, ensure_ascii=False, indent=2)
        os.replace(str(temp_path), str(file_path))
    except (IOError, OSError):
        # Clean up temp file on failure
        try:
            if temp_path.exists():
                os.remove(temp_path)
        except OSError:
            pass
        raise


def _validate_record_input(
    code: str, txn_type: str, amount: Any, valid_codes: set[str]
) -> str | None:
    """Validate /record input fields.

    Returns an error message string if validation fails, or None if valid.
    """
    if code not in valid_codes:
        return f"ETF代码 {code} 不在配置中"

    if txn_type not in ("buy", "sell"):
        return "type 必须为 buy 或 sell"

    try:
        amount_val = float(amount)
    except (TypeError, ValueError):
        return "金额必须为正数且不超过10000000"

    if amount_val <= 0 or amount_val > 10_000_000:
        return "金额必须为正数且不超过10000000"

    return None


@app.route("/record", methods=["POST"])
def record_transaction() -> tuple[Any, int]:
    """Record a buy/sell transaction.

    JSON body: {"code": str, "type": "buy"|"sell", "amount": float}

    Returns:
        200 with success message on successful recording.
        400 on validation errors.
        500 on store write failure.
    """
    data = request.get_json(force=True, silent=True)
    if not data or not isinstance(data, dict):
        return jsonify({"status": "error", "message": "请求体必须为有效JSON"}), 400

    code = str(data.get("code", ""))
    txn_type = str(data.get("type", ""))
    amount = data.get("amount")

    try:
        config = load_config()
    except SystemExit:
        return jsonify({"status": "error", "message": "配置加载失败"}), 500

    valid_codes = {etf.code for etf in config.etfs}

    error_msg = _validate_record_input(code, txn_type, amount, valid_codes)
    if error_msg:
        return jsonify({"status": "error", "message": error_msg}), 400

    amount_val = float(amount)
    type_label = "买入" if txn_type == "buy" else "卖出"

    try:
        store = PositionStore(data_dir=config.data_dir)
        store.append(code, txn_type, amount_val)
    except StoreError:
        return jsonify({"status": "error", "message": "存储写入失败"}), 500

    return jsonify({
        "status": "success",
        "message": f"已记录: {code} {type_label} {amount_val} 元",
    }), 200


@app.route("/telegram/webhook", methods=["POST"])
def telegram_webhook() -> tuple[Any, int]:
    """Handle Telegram Bot webhook updates.

    Parses /buy CODE AMOUNT and /sell CODE AMOUNT commands.
    Replies via Telegram sendMessage API.

    Returns:
        200 always (Telegram expects 200 to acknowledge receipt).
    """
    update = request.get_json(force=True, silent=True)
    if not update or not isinstance(update, dict):
        return jsonify({"ok": True}), 200

    # Extract message text
    message = update.get("message", {})
    if not isinstance(message, dict):
        return jsonify({"ok": True}), 200

    text = message.get("text", "")
    chat_id = message.get("chat", {}).get("id")

    if not text or not chat_id:
        return jsonify({"ok": True}), 200

    # Match /buy CODE AMOUNT or /sell CODE AMOUNT
    pattern = r"^/(buy|sell)\s+(\S+)\s+(\S+)$"
    match = re.match(pattern, text.strip())
    if not match:
        return jsonify({"ok": True}), 200

    txn_type = match.group(1)
    code = match.group(2)
    amount_str = match.group(3)

    # Parse amount
    try:
        amount_val = float(amount_str)
    except (TypeError, ValueError):
        _send_telegram_reply(chat_id, "❌ 金额必须为正数且不超过10000000")
        return jsonify({"ok": True}), 200

    # Load config for validation
    try:
        config = load_config()
    except SystemExit:
        _send_telegram_reply(chat_id, "❌ 配置加载失败")
        return jsonify({"ok": True}), 200

    valid_codes = {etf.code for etf in config.etfs}

    error_msg = _validate_record_input(code, txn_type, amount_val, valid_codes)
    if error_msg:
        _send_telegram_reply(chat_id, f"❌ {error_msg}")
        return jsonify({"ok": True}), 200

    # Record the transaction
    type_label = "买入" if txn_type == "buy" else "卖出"
    try:
        store = PositionStore(data_dir=config.data_dir)
        store.append(code, txn_type, amount_val)
    except StoreError:
        _send_telegram_reply(chat_id, "❌ 记录失败: 存储写入错误")
        return jsonify({"ok": True}), 200

    _send_telegram_reply(chat_id, f"✅ 已记录: {code} {type_label} {amount_val} 元")
    return jsonify({"ok": True}), 200


def _send_telegram_reply(chat_id: int | str, text: str) -> None:
    """Send a reply message via Telegram Bot API.

    Loads config to get bot_token. Logs errors but does not raise.
    """
    try:
        config = load_config()
    except SystemExit:
        logger.error("无法加载配置，Telegram 回复失败")
        return

    bot_token = config.telegram.bot_token
    if not bot_token:
        logger.error("Telegram bot_token 未配置，无法回复")
        return

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    try:
        http_requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=30)
    except Exception as e:
        logger.error("Telegram 回复失败: %s", e)
