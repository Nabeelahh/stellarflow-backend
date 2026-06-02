from __future__ import annotations

import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from network.tx_manager import AtomicIntegerCounter, TxManager


def test_atomic_counter_requires_seed_then_increments() -> None:
    counter = AtomicIntegerCounter()

    with pytest.raises(ValueError, match="seeded"):
        counter.next()

    assert counter.next(seed=42) == 42
    assert counter.next() == 43

    counter.sync(100)
    assert counter.next() == 101

    counter.invalidate()
    with pytest.raises(ValueError, match="seeded"):
        counter.next()


def test_broadcast_signs_sequenced_payload_before_dispatch() -> None:
    manager = TxManager()
    observed = {}

    def signer(payload):
        assert payload["sequence"] == 10
        signed = dict(payload)
        signed["signature"] = f"sig-{payload['sequence']}"
        return signed

    def dispatcher(payload):
        observed.update(payload)
        return {"hash": "ok"}

    result = manager.broadcast(
        "GACCOUNT",
        {"op": "manage_data"},
        signer=signer,
        dispatcher=dispatcher,
        seed_sequence=10,
    )

    assert result.sequence == 10
    assert result.dispatch_result == {"hash": "ok"}
    assert observed == {
        "op": "manage_data",
        "sequence": 10,
        "signature": "sig-10",
    }


def test_parallel_broadcasts_dispatch_in_sequence_order() -> None:
    manager = TxManager()
    dispatched_sequences = []
    dispatched_lock = threading.Lock()

    def signer(payload):
        # Later sequence numbers sign faster. The manager should still keep
        # dispatch ordered because signing and dispatch share one account lock.
        time.sleep(max(0, 0.01 - payload["sequence"] * 0.001))
        signed = dict(payload)
        signed["signature"] = f"sig-{payload['sequence']}"
        return signed

    def dispatcher(payload):
        with dispatched_lock:
            dispatched_sequences.append(payload["sequence"])
        return payload["sequence"]

    def submit(index: int):
        return manager.broadcast(
            "GACCOUNT",
            {"index": index},
            signer=signer,
            dispatcher=dispatcher,
            seed_sequence=1,
        )

    with ThreadPoolExecutor(max_workers=6) as executor:
        results = list(executor.map(submit, range(8)))

    assert sorted(result.sequence for result in results) == list(range(1, 9))
    assert dispatched_sequences == list(range(1, 9))


def test_accounts_have_independent_sequence_counters() -> None:
    manager = TxManager()

    def signer(payload):
        signed = dict(payload)
        signed["signature"] = f"sig-{payload['sequence']}"
        return signed

    def dispatcher(payload):
        return payload["sequence"]

    first = manager.broadcast(
        "GA",
        {"op": "a"},
        signer=signer,
        dispatcher=dispatcher,
        seed_sequence=5,
    )
    second = manager.broadcast(
        "GB",
        {"op": "b"},
        signer=signer,
        dispatcher=dispatcher,
        seed_sequence=90,
    )
    third = manager.broadcast(
        "GA",
        {"op": "a2"},
        signer=signer,
        dispatcher=dispatcher,
    )

    assert first.sequence == 5
    assert second.sequence == 90
    assert third.sequence == 6
