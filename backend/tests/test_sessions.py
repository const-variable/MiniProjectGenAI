from sessions import SessionStore


class ClosingSession:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def test_delete_and_ttl_cleanup_close_sessions():
    store = SessionStore(ttl_seconds=0)
    expired = ClosingSession()
    expired_id = store.create(expired)
    current = ClosingSession()
    current_id = store.create(current)

    assert expired_id != current_id
    assert expired.closed
    assert store.delete(current_id)
    assert current.closed


def test_unknown_delete_returns_false():
    assert not SessionStore().delete("missing")