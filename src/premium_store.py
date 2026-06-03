"""Persistence layer for historical premium rate records."""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

from src.exceptions import StoreError
from src.models import PremiumRecord


class PremiumStore:
    """File-based JSON storage for historical premium records.

    Each ETF gets its own JSON file at {data_dir}/{code}.json containing
    a records array. Records are deduplicated by timestamp (to the second)
    and automatically pruned beyond 30 days.
    """

    _MAX_AGE_DAYS = 30

    def __init__(self, data_dir: str = "data") -> None:
        self._data_dir = Path(data_dir)
        try:
            os.makedirs(self._data_dir, exist_ok=True)
        except OSError as e:
            raise StoreError("init", "", str(e))

    def save(self, code: str, premium_rate: float, timestamp: datetime) -> None:
        """Persist a premium record, deduplicating by timestamp.

        Overwrites any existing record with the same timestamp (to the second).
        Calls _cleanup() to prune records older than 30 days.

        Raises:
            StoreError: If the file cannot be read or written.
        """
        try:
            records = self._read_records(code)
        except StoreError:
            raise

        # Normalize timestamp to second precision (strip microseconds)
        ts_normalized = timestamp.replace(microsecond=0)
        ts_str = ts_normalized.strftime("%Y-%m-%dT%H:%M:%S")

        # Deduplicate: remove any existing record with the same timestamp
        records = [r for r in records if r.get("timestamp") != ts_str]

        # Append the new record
        records.append({
            "premium_rate": premium_rate,
            "timestamp": ts_str,
        })

        # Write back
        self._write_records(code, records)

        # Cleanup old records
        self._cleanup(code)

    def query(self, code: str, lookback_days: int) -> list[PremiumRecord]:
        """Return records within the lookback window, sorted by timestamp ascending.

        Args:
            code: ETF code.
            lookback_days: Number of days to look back from current time.

        Returns:
            List of PremiumRecord within the window, sorted ascending by timestamp.

        Raises:
            StoreError: If the file cannot be read.
        """
        records = self._read_records(code)
        now = datetime.now()
        cutoff = now - timedelta(days=lookback_days)

        result: list[PremiumRecord] = []
        for r in records:
            try:
                ts = datetime.fromisoformat(r["timestamp"])
            except (KeyError, ValueError):
                continue
            if ts >= cutoff:
                result.append(PremiumRecord(
                    code=code,
                    premium_rate=r["premium_rate"],
                    timestamp=ts,
                ))

        result.sort(key=lambda rec: rec.timestamp)
        return result

    def _cleanup(self, code: str) -> None:
        """Remove records older than 30 days from the store file.

        Raises:
            StoreError: If the file cannot be read or written.
        """
        records = self._read_records(code)
        now = datetime.now()
        cutoff = now - timedelta(days=self._MAX_AGE_DAYS)

        filtered = []
        for r in records:
            try:
                ts = datetime.fromisoformat(r["timestamp"])
            except (KeyError, ValueError):
                continue
            if ts >= cutoff:
                filtered.append(r)

        self._write_records(code, filtered)

    def _file_path(self, code: str) -> Path:
        """Return the JSON file path for a given ETF code."""
        return self._data_dir / f"{code}.json"

    def _read_records(self, code: str) -> list[dict]:
        """Read records from the JSON file for an ETF code.

        Returns an empty list if the file doesn't exist.

        Raises:
            StoreError: On IOError or JSON decode failure.
        """
        path = self._file_path(code)
        if not path.exists():
            return []

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (IOError, OSError) as e:
            raise StoreError("read", code, str(e))
        except json.JSONDecodeError as e:
            raise StoreError("read", code, f"JSON 解析失败: {e}")

        if not isinstance(data, dict) or "records" not in data:
            return []

        records = data["records"]
        if not isinstance(records, list):
            return []

        return records

    def _write_records(self, code: str, records: list[dict]) -> None:
        """Write records to the JSON file for an ETF code.

        Raises:
            StoreError: On IOError.
        """
        path = self._file_path(code)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"records": records}, f, ensure_ascii=False, indent=2)
        except (IOError, OSError) as e:
            raise StoreError("write", code, str(e))
