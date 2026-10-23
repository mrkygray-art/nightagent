"""SupabaseStore gives each thread its own client: the client's HTTP/2 connection broke when the demo page's polling
overlapped a create_ticket call on a shared one (NS-4877)."""
import threading

import supabase

from app.store import SupabaseStore


def test_each_thread_gets_its_own_client_and_keeps_it(monkeypatch):
    made = []
    monkeypatch.setattr(supabase, "create_client", lambda url, key: made.append((url, key)) or object())
    store = SupabaseStore("https://x.supabase.co", "key", "ns_")
    seen = {}

    def use(name):
        seen[name] = (store.db, store.db)

    threads = [threading.Thread(target=use, args=(n,)) for n in ("a", "b")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert seen["a"][0] is seen["a"][1] and seen["b"][0] is seen["b"][1]  # reused within a thread
    assert seen["a"][0] is not seen["b"][0]  # never shared between threads
    assert made == [("https://x.supabase.co", "key")] * 2
