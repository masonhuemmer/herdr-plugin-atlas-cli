import json

import pytest

from fakes import FakeHerdr, FakeJira
from ticket_core.marker import Binding
from ticket_core.reconcile import Pane, Snapshot
from ticket_core.status_menu import (
    apply_status, bound_binding, invalidate_status, read_status_capture, write_status_capture,
)


def _snap(*panes):
    return Snapshot(tabs=[], panes=[Pane(pid, "t1", label) for pid, label in panes])


def test_a_pane_with_the_marker_is_bound_to_its_key():
    snap = _snap(("p1", "ticket:v1 EX-5 · Fix login"))
    assert bound_binding(snap, "p1") == Binding("EX-5", "Fix login")


def test_a_pane_without_the_marker_is_not_bound():
    snap = _snap(("p1", "scratch"), ("p2", ""))
    assert bound_binding(snap, "p1") is None
    assert bound_binding(snap, "p2") is None


def test_a_pane_missing_from_the_snapshot_is_not_bound():
    snap = _snap(("p1", "ticket:v1 EX-5 · Fix login"))
    assert bound_binding(snap, "p9") is None


def test_the_status_capture_round_trips(tmp_path):
    write_status_capture(tmp_path / "session", "p4")
    assert read_status_capture(tmp_path / "session") == "p4"


def test_invalidate_removes_only_that_key(tmp_path):
    cache = tmp_path / "statuses.json"
    cache.write_text(json.dumps({"EX-5": {"status": "To Do", "at": 1.0},
                                 "EX-6": {"status": "Done", "at": 1.0}}))
    invalidate_status(cache, "EX-5")
    assert json.loads(cache.read_text()) == {"EX-6": {"status": "Done", "at": 1.0}}


def test_invalidate_without_a_cache_file_does_nothing(tmp_path):
    invalidate_status(tmp_path / "statuses.json", "EX-5")
    assert not (tmp_path / "statuses.json").exists()


class OrderedJira(FakeJira):
    def __init__(self, order):
        super().__init__()
        self.order = order

    def transition(self, key, status, site):
        self.order.append(("transition", key, status))
        super().transition(key, status, site)

    def status(self, key, site):
        self.order.append(("status", key))
        return super().status(key, site)


def _bound_herdr(order, key="EX-5"):
    herdr = FakeHerdr(log=order)
    tab, root = herdr.add_tab("Fix login", "w1", pane_label=f"ticket:v1 {key} · Fix login")
    return herdr, root


def test_a_choice_transitions_then_refreshes_the_cache_then_the_sidebar(tmp_path):
    order = []
    jira = OrderedJira(order)
    jira.statuses = {"EX-5": "Done"}
    herdr, root = _bound_herdr(order)
    apply_status("EX-5", "Done", jira=jira, herdr=herdr, site="acme",
                 cache_path=tmp_path / "statuses.json", sleep=lambda s: None, now=lambda: 10.0)
    assert order == [("transition", "EX-5", "Done"), ("status", "EX-5"),
                     ("report_token", root, "EX-5")]
    assert herdr.statuses == {root: "Done"}


def test_the_refresh_reads_jira_again_instead_of_the_stale_cached_status(tmp_path):
    cache = tmp_path / "statuses.json"
    cache.write_text(json.dumps({"EX-5": {"status": "To Do", "at": 1.0},
                                 "EX-6": {"status": "Done", "at": 1.0}}))
    jira = FakeJira()
    jira.statuses = {"EX-5": "Done"}
    herdr, _ = _bound_herdr([])
    apply_status("EX-5", "Done", jira=jira, herdr=herdr, site="acme", cache_path=cache,
                 sleep=lambda s: None, now=lambda: 10.0)
    saved = json.loads(cache.read_text())
    assert saved["EX-5"] == {"status": "Done", "at": 10.0}
    assert saved["EX-6"] == {"status": "Done", "at": 1.0}  # other keys are untouched


def test_a_failed_transition_leaves_the_cache_and_the_sidebar_alone(tmp_path):
    cache = tmp_path / "statuses.json"
    before = json.dumps({"EX-5": {"status": "To Do", "at": 1.0}})
    cache.write_text(before)
    jira = FakeJira()
    jira.fail_transition = True
    herdr, _ = _bound_herdr([])
    with pytest.raises(RuntimeError, match="transition failed"):
        apply_status("EX-5", "Done", jira=jira, herdr=herdr, site="acme", cache_path=cache,
                     sleep=lambda s: None, now=lambda: 10.0)
    assert cache.read_text() == before
    assert herdr.calls == []
