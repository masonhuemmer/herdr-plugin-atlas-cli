import json

from fakes import FakeHerdr
from ticket_core.adapters.jira import AtlasError
from ticket_core.reconcile import Pane, Snapshot, Tab, TokenChange, reconcile
from ticket_core.sync import fetch_statuses, sync_tokens


class StatusJira:
    def __init__(self, statuses, fail=()):
        self.statuses = statuses
        self.fail = set(fail)
        self.calls: list[str] = []

    def status(self, key, site):
        self.calls.append(key)
        if key in self.fail:
            raise AtlasError("boom")
        return self.statuses.get(key)


def _snap(*labels):
    tabs = [Tab(f"t{i}", label) for i, label in enumerate(labels)]
    panes = [Pane(f"p{i}", f"t{i}") for i in range(len(labels))]
    return Snapshot(tabs=tabs, panes=panes)


def test_reconcile_carries_the_status_for_a_bound_pane():
    snap = _snap("ticket:v1 SDO-1 · Login")
    assert reconcile(snap, {"SDO-1": "In Progress"}) == [TokenChange("p0", "SDO-1", "In Progress")]


def test_reconcile_without_a_status_leaves_it_none():
    snap = _snap("ticket:v1 SDO-1 · Login")
    assert reconcile(snap, {}) == [TokenChange("p0", "SDO-1", None)]


def test_fetch_statuses_asks_jira_once_per_key():
    jira = StatusJira({"SDO-1": "Done"})
    snap = _snap("ticket:v1 SDO-1 · a", "ticket:v1 SDO-1 · b")
    assert fetch_statuses(snap, jira, "acme", None, now=lambda: 0.0) == {"SDO-1": "Done"}
    assert jira.calls == ["SDO-1"]


def test_cached_status_is_reused_within_the_ttl(tmp_path):
    cache = tmp_path / "statuses.json"
    snap = _snap("ticket:v1 SDO-1 · a")
    fetch_statuses(snap, StatusJira({"SDO-1": "To Do"}), "acme", cache, now=lambda: 100.0)
    later = StatusJira({"SDO-1": "Done"})
    got = fetch_statuses(snap, later, "acme", cache, now=lambda: 200.0)
    assert got == {"SDO-1": "To Do"} and later.calls == []


def test_expired_cache_is_refreshed(tmp_path):
    cache = tmp_path / "statuses.json"
    snap = _snap("ticket:v1 SDO-1 · a")
    fetch_statuses(snap, StatusJira({"SDO-1": "To Do"}), "acme", cache, now=lambda: 100.0)
    got = fetch_statuses(snap, StatusJira({"SDO-1": "Done"}), "acme", cache, now=lambda: 1000.0)
    assert got == {"SDO-1": "Done"}


def test_jira_failure_leaves_the_status_out_and_is_not_cached(tmp_path):
    cache = tmp_path / "statuses.json"
    snap = _snap("ticket:v1 SDO-1 · a")
    assert fetch_statuses(snap, StatusJira({}, fail={"SDO-1"}), "acme", cache, now=lambda: 0.0) == {}
    assert not cache.exists() or "SDO-1" not in json.loads(cache.read_text())


def test_sync_tokens_reports_key_and_status():
    herdr = FakeHerdr()
    tab, root = herdr.add_tab("ticket:v1 SDO-5 · Fix login", "w1")
    sync_tokens(herdr, jira=StatusJira({"SDO-5": "In Progress"}), site="acme",
                sleep=lambda s: None, now=lambda: 0.0)
    assert herdr.tokens == {root: "SDO-5"}
    assert herdr.statuses == {root: "In Progress"}
