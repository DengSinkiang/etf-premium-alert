"""HTTP API for the QDII ETF Premium Monitor.

Provides a Flask-based HTTP interface for triggering the monitoring workflow
via Cloudflare Worker or other HTTP clients.
"""

import logging
from datetime import datetime
from typing import Any

from flask import Flask, jsonify

from src.config import load_config
from src.models import MonitorResult
from src.monitor import Monitor

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
    try:
        config = load_config()
        monitor = Monitor(config)
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
