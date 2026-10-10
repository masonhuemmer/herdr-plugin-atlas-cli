import threading
from datetime import datetime

import pytest

from fakes import Crash, FakeHerdr, FakeJira, Interrupted
from ticket_core.state import Busy, StateStore
from ticket_core.transactions import (
    Capture,
    Refused,
    apply_site_change,
    create_ticket,
    discard,
    lookup_bind,
)

NOW = datetime(2026, 10, 9, 14, 10)
CAPTURE = Capture(workspace_id="w1", cwd="/work")
CREATE_KW = dict(project="SDO", issue_type="Task", assignee="acc-1")


@pytest.fixture
def store(tmp_path):
    return StateStore(tmp_path / "session" / "state.json")


def _create(store, herdr, jira, description="  Fix login  ", site="acme", **kw):
    return create_ticket(
        store, herdr, jira, CAPTURE, description, site=site, now=NOW, **CREATE_KW, **kw
    )


def _create_crashing_at(store, herdr, jira, at, **kw):
    with pytest.raises(Interrupted):
        _create(store, herdr, jira, checkpoint=Crash(at), **kw)


def test_lookup_binds_tab_and_reports_token(store):
    herdr, jira = FakeHerdr(), FakeJira()
    lookup_bind(store, herdr, CAPTURE, "SDO-5", "Fix login", site="acme")

    [(tab_id, tab)] = herdr.tabs.items()
    assert tab["label"] == "Fix login"
    assert herdr.labels == {tab["root"]: "ticket:v1 SDO-5 · Fix login"}
    assert herdr.tokens == {tab["root"]: "SDO-5"}
    assert jira.creates == []
    state = store.read()
    assert state.pending is None
    assert state.site == "acme"


def test_create_runs_steps_in_order_and_clears_pending(store):
    log = []
    herdr, jira = FakeHerdr(log=log), FakeJira(keys=["SDO-9"], log=log)
    _create(store, herdr, jira, checkpoint=log.append)

    assert log == [
        "creating",
        "jira.create",
        "jira_call",
        "jira_created",
        "tab_creating",
        ("tab_create", "w1", "/work", "Fix login"),
        "tab_call",
        ("pane_rename", "p2", "ticket:v1 SDO-9 · Fix login"),
        "tab_created",
        ("report_token", "p2", "SDO-9"),
    ]
    assert jira.creates == [
        dict(project="SDO", issue_type="Task", summary="Fix login",
             assignee="acc-1", site="acme")
    ]
    assert store.read().pending is None
    assert store.read().site == "acme"


def test_create_sends_normalised_description_as_summary(store):
    herdr, jira = FakeHerdr(), FakeJira(keys=["SDO-9"])
    _create(store, herdr, jira, description=" a*b? ")
    assert jira.creates[0]["summary"] == "ab"


def test_create_with_empty_description_is_refused_before_jira(store):
    herdr, jira = FakeHerdr(), FakeJira(keys=["SDO-9"])
    with pytest.raises(Refused):
        _create(store, herdr, jira, description=" *? ")
    assert jira.creates == []
    assert store.read().pending is None


def test_lookup_and_create_refused_while_pending_exists(store):
    herdr, jira = FakeHerdr(), FakeJira(keys=["SDO-9"])
    _create_crashing_at(store, herdr, jira, "creating")
    with pytest.raises(Refused):
        lookup_bind(store, herdr, CAPTURE, "SDO-5", "x", site="acme")
    with pytest.raises(Refused):
        _create(store, herdr, jira, description="second")
    assert jira.creates == []  # the interrupted create never reached Jira, and the second was refused


def test_failing_jira_create_leaves_creating_record(store):
    herdr, jira = FakeHerdr(), FakeJira(keys=["SDO-9"], fail_on_create=True)
    with pytest.raises(RuntimeError):
        _create(store, herdr, jira)
    pending = store.read().pending
    assert pending.stage == "creating"
    assert pending.description == "Fix login"
    assert pending.started_at == NOW


def test_concurrent_creates_make_one_jira_call_and_one_record(store):
    gate = threading.Event()
    herdr = FakeHerdr()
    jira = FakeJira(keys=["SDO-1", "SDO-2"], gate=gate)
    first = threading.Thread(target=_create, args=(store, herdr, jira, "one"))
    first.start()
    assert jira.entered.wait(5)

    with pytest.raises(Busy):
        _create(store, herdr, jira, description="two")
    assert store.read().pending.stage == "creating"

    gate.set()
    first.join(5)
    assert [c["summary"] for c in jira.creates] == ["one"]


def test_apply_site_change_unbinds_marked_tabs_and_clears_pending(store):
    herdr, jira = FakeHerdr(), FakeJira(keys=["SDO-9"])
    lookup_bind(store, herdr, CAPTURE, "SDO-5", "Fix login", site="A")
    _create_crashing_at(store, herdr, jira, "creating", description="pending", site="A")
    [(tab_id, tab)] = herdr.tabs.items()

    apply_site_change(store, herdr, "B")

    assert tab["label"] == "Fix login"
    assert herdr.labels == {}
    assert herdr.tokens == {}
    state = store.read()
    assert state.site == "B"
    assert state.pending is None


def test_apply_site_change_with_same_site_changes_nothing(store):
    herdr = FakeHerdr()
    lookup_bind(store, herdr, CAPTURE, "SDO-5", "Fix login", site="A")
    calls_before = len(herdr.calls)

    apply_site_change(store, herdr, "A")

    assert len(herdr.calls) == calls_before
    assert herdr.tokens != {}
    assert store.read().site == "A"


def test_discard_clears_pending_and_keeps_site(store):
    herdr, jira = FakeHerdr(), FakeJira(keys=["SDO-9"])
    _create_crashing_at(store, herdr, jira, "creating")
    discard(store)
    state = store.read()
    assert state.pending is None
    assert state.site == "acme"
