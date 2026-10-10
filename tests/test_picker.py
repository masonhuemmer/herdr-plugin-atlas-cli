from datetime import datetime

import pytest

from fakes import Crash, FakeHerdr, FakeJira, Interrupted
from ticket_core.recovery import Issue, Prompt
from ticket_core.picker import Picker, crash_checkpoint, read_capture, write_capture
from ticket_core.state import Pending, State, StateStore
from ticket_core.transactions import Refused

NOW = datetime(2026, 10, 10, 9, 0)


@pytest.fixture
def parts(tmp_path):
    store = StateStore(tmp_path / "session" / "state.json")
    herdr, jira = FakeHerdr(), FakeJira(keys=["SDO-9"], search_results=[Issue("SDO-9", "Fix login")])
    write_capture(tmp_path / "session", "w1", "/work")

    def make(checkpoint=None):
        return Picker(store=store, herdr=herdr, jira=jira, site="acme", project="SDO",
                      issue_type="Task", assignee="acc-1",
                      capture=read_capture(tmp_path / "session"), now=lambda: NOW,
                      checkpoint=checkpoint or (lambda name: None),
                      sleep=lambda s: None)
    return store, herdr, jira, make


def test_skip_makes_a_plain_tab_with_no_label(parts):
    _, herdr, _, make = parts
    make().skip()
    assert ("tab_create", "w1", "/work", None) in herdr.calls
    assert herdr.tokens == {}


def test_bind_labels_the_tab_and_reports_the_token(parts):
    _, herdr, _, make = parts
    make().bind(Issue("SDO-5", "Fix login"))
    [(tid, tab)] = [(t, v) for t, v in herdr.tabs.items()]
    assert tab["label"] == "ticket:v1 SDO-5 · Fix login"
    assert herdr.tokens == {tab["root"]: "SDO-5"}


def test_create_makes_the_ticket_then_the_bound_tab(parts):
    _, herdr, jira, make = parts
    make().create("  Fix login  ")
    assert jira.creates[0]["summary"] == "Fix login"
    assert jira.creates[0]["site"] == "acme"
    [(tid, tab)] = list(herdr.tabs.items())
    assert tab["label"] == "ticket:v1 SDO-9 · Fix login"
    assert herdr.tokens == {tab["root"]: "SDO-9"}


def test_bind_and_create_are_refused_while_a_pending_record_exists(parts):
    store, _, _, make = parts
    store.write(State(site="acme", pending=Pending(
        stage="creating", started_at=NOW, description="x", key=None, workspace_id="w1",
        cwd="/work", tab_label=None, tab_id=None, root_pane_id=None)))
    picker = make()
    with pytest.raises(Refused):
        picker.bind(Issue("SDO-5", "Fix login"))
    with pytest.raises(Refused):
        picker.create("Fix login")


def test_start_offers_the_uncertain_create_and_confirm_finishes_it(parts):
    _, herdr, jira, make = parts
    with pytest.raises(Interrupted):
        make(checkpoint=Crash("jira_call")).create("Fix login")

    picker = make()
    prompt = picker.start()
    assert prompt == Prompt([Issue("SDO-9", "Fix login")], [])
    picker.answer(("confirm", "SDO-9"))
    assert len(jira.creates) == 1
    [(tid, tab)] = list(herdr.tabs.items())
    assert herdr.tokens == {tab["root"]: "SDO-9"}


def test_start_with_nothing_pending_returns_none(parts):
    _, _, _, make = parts
    assert make().start() is None


def test_crash_checkpoint_exits_only_at_the_named_point():
    exits = []
    cp = crash_checkpoint({"HERDR_TICKET_CRASH_AT": "jira_call"}, exit=exits.append)
    cp("creating")
    assert exits == []
    cp("jira_call")
    assert exits == [75]


def test_crash_checkpoint_is_inert_when_unset():
    exits = []
    cp = crash_checkpoint({}, exit=exits.append)
    for name in ("creating", "jira_call", "tab_created"):
        cp(name)
    assert exits == []
