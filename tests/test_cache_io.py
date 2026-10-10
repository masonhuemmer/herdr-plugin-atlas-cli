import json

from ticket_core.status_menu import invalidate_status
from ticket_core.sync import fetch_statuses, load_cache
from ticket_core.reconcile import Pane, Snapshot, Tab


def test_corrupt_cache_reads_as_empty(tmp_path):
    cache = tmp_path / "statuses.json"
    cache.write_text('{"SDO-1": {"status": "To Do", "at": 1}}\n}')
    assert load_cache(cache) == {}


def test_missing_cache_reads_as_empty(tmp_path):
    assert load_cache(tmp_path / "nope.json") == {}


def test_invalidate_repairs_a_corrupt_cache(tmp_path):
    cache = tmp_path / "statuses.json"
    cache.write_text('{"SDO-1": {"status": "To Do", "at": 1}}\n}')
    invalidate_status(cache, "SDO-1")  # must not raise
    assert json.loads(cache.read_text()) == {}


def test_writes_leave_no_partial_or_temp_files(tmp_path):
    cache = tmp_path / "statuses.json"

    class Jira:
        def status(self, key, site):
            return "To Do"

    snap = Snapshot([Tab("t1", "a")], [Pane("p1", "t1", label="ticket:v1 SDO-1 · a")])
    fetch_statuses(snap, Jira(), "acme", cache, now=lambda: 1.0)
    assert json.loads(cache.read_text()) == {"SDO-1": {"status": "To Do", "at": 1.0}}
    assert sorted(p.name for p in tmp_path.iterdir()) == ["statuses.json"]
