"""Persistent daily and lifetime budget for query embeddings paid with the owner's Voyage key.

Counters live in Qdrant (the deployed host restarts often and loses memory). Used by
`GuardedEmbeddings` before every Voyage call; fails closed when spent or when it can't save.
"""

import threading
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal

from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct


class BudgetSpent(Exception):
    """The daily or the lifetime embedding budget has no room (raised by `EmbedBudget.spend`)."""

    def __init__(self, which: Literal["daily", "total"]) -> None:
        super().__init__(which)
        self.which = which


class DailyBudgetSpent(BudgetSpent):
    """Today's budget is spent (own class so the API can give it its own message)."""

    def __init__(self) -> None:
        super().__init__("daily")


class TotalBudgetSpent(BudgetSpent):
    """The lifetime budget is spent (own class so the API can give it its own message)."""

    def __init__(self) -> None:
        super().__init__("total")


def _point_id(name: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, name))


class EmbedBudget:
    """Counts query embeddings per UTC day and in total, persisted in a vector-less collection.

    Called by `GuardedEmbeddings`; check and record share one lock so threads can't overspend,
    and a failed save rolls the counts back and refuses the spend (fail closed).
    """

    def __init__(
        self,
        client: QdrantClient,
        collection: str,
        daily: int,
        total: int,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.client = client
        self.collection = collection
        self.daily_cap = daily
        self.total_cap = total
        self.clock = clock
        self._lock = threading.Lock()
        self._day: str | None = None
        self._day_count = 0
        self._total_count = 0
        self._total_id = _point_id("gradpath:embed:total")

    def _today(self) -> str:
        return datetime.fromtimestamp(self.clock(), UTC).strftime("%Y-%m-%d")

    @staticmethod
    def _day_id(day: str) -> str:
        return _point_id(f"gradpath:embed:day:{day}")

    def _load(self, day: str) -> None:
        """Read both counters from Qdrant (first use, and whenever the UTC day changes)."""
        if not self.client.collection_exists(self.collection):
            self.client.create_collection(self.collection, vectors_config={})
        day_id = self._day_id(day)
        points = self.client.retrieve(
            self.collection, ids=[self._total_id, day_id], with_payload=True
        )
        by_id = {str(p.id): (p.payload or {}) for p in points}
        self._total_count = int(by_id.get(self._total_id, {}).get("count", 0))
        self._day_count = int(by_id.get(day_id, {}).get("count", 0))
        self._day = day

    def spend(self, n: int) -> None:
        """Reserve `n` embeddings or raise `BudgetSpent`; any Qdrant failure also refuses."""
        with self._lock:
            day = self._today()
            if self._day != day:
                self._load(day)
            if self._day_count + n > self.daily_cap:
                raise DailyBudgetSpent
            if self._total_count + n > self.total_cap:
                raise TotalBudgetSpent
            self._day_count += n
            self._total_count += n
            try:
                self._save(day)
            except Exception:
                self._day_count -= n
                self._total_count -= n
                raise

    def refund(self, n: int) -> None:
        """Give back `n` reserved embeddings whose Voyage call failed (`GuardedEmbeddings`): a
        refused request (a full free-tier window, Voyage's 429) must not burn the budget. Only
        within the same UTC day; if saving fails the higher count stays (the safe side)."""
        with self._lock:
            if self._day != self._today():
                return
            day_count, total_count = self._day_count, self._total_count
            self._day_count = max(0, day_count - n)
            self._total_count = max(0, total_count - n)
            try:
                self._save(self._day)
            except Exception:
                self._day_count, self._total_count = day_count, total_count

    def _save(self, day: str) -> None:
        """Write both counters (called under the lock by `spend` and `refund`)."""
        self.client.upsert(
            self.collection,
            points=[
                PointStruct(id=self._total_id, vector={}, payload={"count": self._total_count}),
                PointStruct(
                    id=self._day_id(day), vector={}, payload={"count": self._day_count, "day": day}
                ),
            ],
        )
