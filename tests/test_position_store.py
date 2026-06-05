"""Unit tests for PositionStore."""

import json
import os
import tempfile

import pytest

from src.exceptions import StoreError
from src.models import Transaction
from src.position_store import PositionStore


@pytest.fixture
def tmp_data_dir(tmp_path):
    """Provide a temporary data directory for tests."""
    return str(tmp_path)


@pytest.fixture
def store(tmp_data_dir):
    """Create a PositionStore with a temp data directory."""
    return PositionStore(data_dir=tmp_data_dir)


class TestPositionStoreInit:
    def test_file_path_set_correctly(self, tmp_data_dir):
        store = PositionStore(data_dir=tmp_data_dir)
        assert store._file_path.name == "positions.json"
        assert str(store._file_path.parent) == tmp_data_dir


class TestAppend:
    def test_append_creates_file_when_missing(self, store, tmp_data_dir):
        txn = store.append("513500", "buy", 5000.0)
        assert isinstance(txn, Transaction)
        assert txn.code == "513500"
        assert txn.type == "buy"
        assert txn.amount == 5000.0
        assert os.path.exists(os.path.join(tmp_data_dir, "positions.json"))

    def test_append_rounds_amount_to_2dp(self, store):
        txn = store.append("513500", "buy", 5000.555)
        assert txn.amount == 5000.56

    def test_append_multiple_transactions(self, store):
        store.append("513500", "buy", 5000.0)
        store.append("513500", "sell", 3000.0)
        store.append("513650", "buy", 2000.0)

        txns_500 = store.get_transactions("513500")
        assert len(txns_500) == 2
        assert txns_500[0].type == "buy"
        assert txns_500[1].type == "sell"

        txns_650 = store.get_transactions("513650")
        assert len(txns_650) == 1

    def test_append_returns_transaction_with_timestamp(self, store):
        txn = store.append("513500", "buy", 1000.0)
        # Timestamp should be ISO 8601 with second precision
        assert "T" in txn.timestamp
        assert len(txn.timestamp) == 19  # "2024-01-15T10:30:00"


class TestGetTransactions:
    def test_returns_empty_list_when_file_missing(self, store):
        result = store.get_transactions("513500")
        assert result == []

    def test_returns_empty_list_when_code_has_no_records(self, store):
        store.append("513500", "buy", 5000.0)
        result = store.get_transactions("999999")
        assert result == []

    def test_returns_only_transactions_for_given_code(self, store):
        store.append("513500", "buy", 5000.0)
        store.append("513650", "buy", 3000.0)
        store.append("513500", "sell", 2000.0)

        result = store.get_transactions("513500")
        assert len(result) == 2
        assert all(t.code == "513500" for t in result)

    def test_raises_store_error_on_corrupted_json(self, store, tmp_data_dir):
        # Write corrupted JSON
        path = os.path.join(tmp_data_dir, "positions.json")
        with open(path, "w") as f:
            f.write("{invalid json content")

        with pytest.raises(StoreError) as exc_info:
            store.get_transactions("513500")
        assert "JSON 解析失败" in str(exc_info.value)


class TestComputeEffectiveAmount:
    def test_no_transactions_returns_base_amount(self, store):
        result = store.compute_effective_amount("513500", 10000.0)
        assert result == 10000.0

    def test_buys_increase_effective_amount(self, store):
        store.append("513500", "buy", 5000.0)
        store.append("513500", "buy", 3000.0)
        result = store.compute_effective_amount("513500", 10000.0)
        assert result == 18000.0

    def test_sells_decrease_effective_amount(self, store):
        store.append("513500", "sell", 3000.0)
        result = store.compute_effective_amount("513500", 10000.0)
        assert result == 7000.0

    def test_clamps_to_zero_when_negative(self, store):
        store.append("513500", "sell", 15000.0)
        result = store.compute_effective_amount("513500", 10000.0)
        assert result == 0.0

    def test_mixed_buys_and_sells(self, store):
        store.append("513500", "buy", 5000.0)
        store.append("513500", "sell", 3000.0)
        store.append("513500", "buy", 2000.0)
        # effective = 10000 + 5000 - 3000 + 2000 = 14000
        result = store.compute_effective_amount("513500", 10000.0)
        assert result == 14000.0

    def test_only_counts_matching_code(self, store):
        store.append("513500", "buy", 5000.0)
        store.append("513650", "buy", 9000.0)
        result = store.compute_effective_amount("513500", 10000.0)
        assert result == 15000.0


class TestErrorHandling:
    def test_missing_file_returns_empty_list(self, store):
        assert store.get_transactions("513500") == []

    def test_corrupted_json_raises_store_error(self, store, tmp_data_dir):
        path = os.path.join(tmp_data_dir, "positions.json")
        with open(path, "w") as f:
            f.write("not valid json")

        with pytest.raises(StoreError):
            store.get_transactions("513500")

    def test_empty_file_returns_empty_list(self, store, tmp_data_dir):
        # Empty dict without "transactions" key
        path = os.path.join(tmp_data_dir, "positions.json")
        with open(path, "w") as f:
            json.dump({}, f)

        result = store.get_transactions("513500")
        assert result == []

    def test_transactions_not_a_list_returns_empty(self, store, tmp_data_dir):
        path = os.path.join(tmp_data_dir, "positions.json")
        with open(path, "w") as f:
            json.dump({"transactions": "not a list"}, f)

        result = store.get_transactions("513500")
        assert result == []
