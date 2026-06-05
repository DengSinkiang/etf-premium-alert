"""Persistence layer for position tracking transactions."""

import json
import os
from datetime import datetime
from pathlib import Path

from src.exceptions import StoreError
from src.models import Transaction


class PositionStore:
    """JSON file-based persistence for position transactions.

    File: data/positions.json
    Format: {"transactions": [{"code": ..., "type": ..., "amount": ..., "timestamp": ...}, ...]}

    All ETFs share a single positions.json file. Transactions are appended
    atomically using a temp file + os.replace pattern.
    """

    def __init__(self, data_dir: str = "data") -> None:
        self._file_path = Path(data_dir) / "positions.json"

    def append(self, code: str, txn_type: str, amount: float) -> Transaction:
        """Append a transaction with current timestamp.

        Args:
            code: ETF code (e.g. "513500").
            txn_type: Transaction type, "buy" or "sell".
            amount: Yuan amount (will be rounded to 2 decimal places).

        Returns:
            The Transaction record that was persisted.

        Raises:
            StoreError: On filesystem read or write failure.
        """
        transactions = self._read_transactions()

        timestamp = datetime.now().replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%S")
        rounded_amount = round(amount, 2)

        record = {
            "code": code,
            "type": txn_type,
            "amount": rounded_amount,
            "timestamp": timestamp,
        }
        transactions.append(record)

        self._write_transactions(transactions)

        return Transaction(
            code=code,
            type=txn_type,
            amount=rounded_amount,
            timestamp=timestamp,
        )

    def get_transactions(self, code: str) -> list[Transaction]:
        """Get all transactions for an ETF code.

        Returns empty list if file doesn't exist or code has no records.

        Args:
            code: ETF code to filter by.

        Returns:
            List of Transaction records for the given code.

        Raises:
            StoreError: On corrupted JSON or I/O read failure.
        """
        transactions = self._read_transactions()
        return [
            Transaction(
                code=t["code"],
                type=t["type"],
                amount=t["amount"],
                timestamp=t["timestamp"],
            )
            for t in transactions
            if t.get("code") == code
        ]

    def undo_last(self) -> Transaction | None:
        """Remove and return the most recent transaction.

        Returns None if no transactions exist.

        Raises:
            StoreError: On filesystem read or write failure.
        """
        transactions = self._read_transactions()
        if not transactions:
            return None

        removed = transactions.pop()
        self._write_transactions(transactions)

        return Transaction(
            code=removed["code"],
            type=removed["type"],
            amount=removed["amount"],
            timestamp=removed["timestamp"],
        )

    def compute_effective_amount(self, code: str, base_amount: float) -> float:
        """Compute effective bought amount from base + buys - sells, clamped to >= 0.

        Args:
            code: ETF code to compute for.
            base_amount: The base bought_amount from config.

        Returns:
            max(0, base_amount + sum(buys) - sum(sells))

        Raises:
            StoreError: On corrupted JSON or I/O read failure.
        """
        transactions = self._read_transactions()

        total_buys = sum(
            t["amount"] for t in transactions
            if t.get("code") == code and t.get("type") == "buy"
        )
        total_sells = sum(
            t["amount"] for t in transactions
            if t.get("code") == code and t.get("type") == "sell"
        )

        return max(0.0, base_amount + total_buys - total_sells)

    def _read_transactions(self) -> list[dict]:
        """Read all transactions from the JSON file.

        Returns an empty list if the file doesn't exist.

        Raises:
            StoreError: On IOError or JSON decode failure.
        """
        if not self._file_path.exists():
            return []

        try:
            with open(self._file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (IOError, OSError) as e:
            raise StoreError("read", "positions", str(e))
        except json.JSONDecodeError as e:
            raise StoreError("read", "positions", f"JSON 解析失败: {e}")

        if not isinstance(data, dict) or "transactions" not in data:
            return []

        transactions = data["transactions"]
        if not isinstance(transactions, list):
            return []

        return transactions

    def _write_transactions(self, transactions: list[dict]) -> None:
        """Write transactions atomically to the JSON file.

        Uses a temporary file and os.replace() for atomic swap, ensuring
        the original file remains unchanged if the write fails.

        Raises:
            StoreError: On write or replace failure. Temp file is cleaned up.
        """
        # Ensure parent directory exists
        try:
            os.makedirs(self._file_path.parent, exist_ok=True)
        except OSError as e:
            raise StoreError("write", "positions", str(e))

        temp_path = self._file_path.with_suffix(".json.tmp")

        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump({"transactions": transactions}, f, ensure_ascii=False, indent=2)
        except (IOError, OSError) as e:
            try:
                if temp_path.exists():
                    os.remove(temp_path)
            except OSError:
                pass
            raise StoreError("write", "positions", str(e))

        try:
            os.replace(str(temp_path), str(self._file_path))
        except OSError as e:
            try:
                if temp_path.exists():
                    os.remove(temp_path)
            except OSError:
                pass
            raise StoreError("write", "positions", str(e))
