"""In-memory store: session_id -> TableRAGSession, expiring after an idle TTL."""
import threading
import time
import uuid


class SessionStore:
    def __init__(self, ttl_seconds: int = 3600):
        self._sessions = {}
        self._lock = threading.Lock()
        self.ttl = ttl_seconds

    def _cleanup(self):
        current_time = time.time()
        expired_session_ids = [session_id for session_id, (_, last_active)
                               in self._sessions.items()
                               if current_time - last_active > self.ttl]
        for session_id in expired_session_ids:
            session, _ = self._sessions.pop(session_id)
            session.close()

    def create(self, session) -> str:
        session_id = uuid.uuid4().hex
        with self._lock:
            self._cleanup()
            self._sessions[session_id] = [session, time.time()]
        return session_id

    def get(self, session_id: str):
        with self._lock:
            session_record = self._sessions.get(session_id)
            if not session_record:
                return None
            session_record[1] = time.time()
            return session_record[0]

    def delete(self, session_id: str) -> bool:
        with self._lock:
            session_record = self._sessions.pop(session_id, None)
            if session_record is None:
                return False
            session_record[0].close()
            return True
