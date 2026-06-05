"""Status tracking for the ETF Premium Monitor."""

import json
import os
from datetime import datetime
from pathlib import Path


class StatusStore:
    """Tracks monitoring status: last success time, consecutive failures per ETF.

    File: data/status.json
    """

    def __init__(self, data_dir: str = "data") -> None:
        self._file_path = Path(data_dir) / "status.json"

    def record_success(self, code: str) -> None:
        """Record a successful monitoring result for an ETF."""
        status = self._read()
        now = datetime.now().replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%S")

        status["last_success_time"] = now
        status.setdefault("etf_status", {})
        status["etf_status"][code] = {
            "last_success": now,
            "consecutive_failures": 0,
        }
        self._write(status)

    def record_failure(self, code: str) -> int:
        """Record a failed monitoring result for an ETF.

        Returns the new consecutive failure count.
        """
        status = self._read()
        status.setdefault("etf_status", {})
        etf = status["etf_status"].setdefault(code, {
            "last_success": None,
            "consecutive_failures": 0,
        })
        etf["consecutive_failures"] = etf.get("consecutive_failures", 0) + 1
        self._write(status)
        return etf["consecutive_failures"]

    def get_status(self) -> dict:
        """Get the full status dict for /status command."""
        return self._read()

    def _read(self) -> dict:
        if not self._file_path.exists():
            return {"last_success_time": None, "etf_status": {}}
        try:
            with open(self._file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return {"last_success_time": None, "etf_status": {}}
            return data
        except (IOError, json.JSONDecodeError):
            return {"last_success_time": None, "etf_status": {}}

    def _write(self, status: dict) -> None:
        os.makedirs(self._file_path.parent, exist_ok=True)
        temp_path = self._file_path.with_suffix(".json.tmp")
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(status, f, ensure_ascii=False, indent=2)
            os.replace(str(temp_path), str(self._file_path))
        except (IOError, OSError):
            try:
                if temp_path.exists():
                    os.remove(temp_path)
            except OSError:
                pass
