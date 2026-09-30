"""In-memory store: session_id -> TableRAGSession, expiring after an idle TTL."""
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
            session, _ = self._items.pop(sid)
            session.close()

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
            item = self._items.pop(sid, None)
            if item is None:
                return False
            item[0].close()
            return True
