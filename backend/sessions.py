"""In-memory store: session_id -> Engine. Sessions expire after an hour of inactivity."""
import threading
import time
import uuid


class SessionStore:
    def __init__(self, ttl_seconds: int = 3600):
        self._items = {}
        self._lock = threading.Lock()
        self.ttl = ttl_seconds

    def _cleanup(self):
        now = time.time()
        for sid in [s for s, (_, t) in self._items.items() if now - t > self.ttl]:
            del self._items[sid]

    def create(self, engine) -> str:
        sid = uuid.uuid4().hex
        with self._lock:
            self._cleanup()
            self._items[sid] = [engine, time.time()]
        return sid

    def get(self, sid: str):
        with self._lock:
            item = self._items.get(sid)
            if not item:
                return None
            item[1] = time.time()
            return item[0]

    def delete(self, sid: str) -> bool:
        with self._lock:
            return self._items.pop(sid, None) is not None
