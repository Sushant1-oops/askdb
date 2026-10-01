"""In-memory, per-connection query history (newest first).

Feeds the Overview page (recent activity, usage stats) and the SQL editor's
"recent queries". Bounded, thread-safe, and intentionally ephemeral: it lives
only as long as the connection does.
"""

from __future__ import annotations

import threading
import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Optional


class HistoryStore:
    def __init__(self, max_per_connection: int = 200) -> None:
        self._max = max_per_connection
        self._items: Dict[str, Deque[Dict[str, Any]]] = defaultdict(lambda: deque(maxlen=self._max))
        self._lock = threading.Lock()

    def add(
        self,
        connection_id: str,
        *,
        source: str,
        sql: Optional[str],
        status: str,
        question: Optional[str] = None,
        row_count: Optional[int] = None,
        duration_ms: Optional[int] = None,
        verdict: Optional[str] = None,
    ) -> Dict[str, Any]:
        entry = {
            "id": uuid.uuid4().hex[:12],
            "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "source": source,  
            "question": question,
            "sql": sql,
            "status": status,  
            "row_count": row_count,
            "duration_ms": duration_ms,
            "verdict": verdict,
        }
        with self._lock:
            self._items[connection_id].appendleft(entry)
        return entry

    def list(self, connection_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._items.get(connection_id, ()))[:limit]

    def stats(self, connection_id: str) -> Dict[str, Any]:
        with self._lock:
            items = list(self._items.get(connection_id, ()))
        today = datetime.now(timezone.utc).date().isoformat()
        succeeded = [i for i in items if i["status"] == "success"]
        durations = [i["duration_ms"] for i in succeeded if i["duration_ms"] is not None]
        return {
            "total": len(items),
            "succeeded": len(succeeded),
            "failed": sum(1 for i in items if i["status"] in ("failed", "blocked")),
            "today": sum(1 for i in items if i["created_at"].startswith(today)),
            "avg_ms": int(sum(durations) / len(durations)) if durations else None,
        }

    def clear(self, connection_id: str) -> None:
        with self._lock:
            self._items.pop(connection_id, None)
