from datetime import datetime

from ticket_core.recovery import Issue, Prompt, ResumeAt, plan_recovery
from ticket_core.reconcile import Tab, reconcile
from ticket_core.state import Pending


def _pending(stage, key="SDO-9", workspace_id="w1"):
    return Pending(
        stage=stage,
        started_at=datetime(2026, 10, 9, 14, 10),
        description="Fix login",
        key=key,
        workspace_id=workspace_id,
        cwd="/work",
        tab_label=f"ticket:v1 {key} · Fix login" if key else None,
        tab_id=None,
        root_pane_id=None,
    )


def test_creating_asks_with_candidates_even_when_empty():
    assert plan_recovery(_pending("creating", key=None), [], []) == Prompt([], [])
    issue = Issue("SDO-9", "Fix login")
    assert plan_recovery(_pending("creating", key=None), [issue], []) == Prompt([issue], [])


def test_jira_created_resumes_at_tab():
    assert plan_recovery(_pending("jira_created"), [], []) == ResumeAt("tab")


def test_tab_created_resumes_at_report():
    assert plan_recovery(_pending("tab_created"), [], []) == ResumeAt("report")


def test_tab_creating_adopts_the_single_match_in_the_workspace():
    tabs = [Tab("t1", "ticket:v1 SDO-9 · Fix login", workspace_id="w1")]
    assert plan_recovery(_pending("tab_creating"), [], tabs) == ResumeAt("adopt", "t1")


def test_tab_creating_asks_when_no_tab_matches():
    assert plan_recovery(_pending("tab_creating"), [], []) == Prompt([], [])


def test_tab_creating_asks_when_several_tabs_match():
    tabs = [
        Tab("t1", "ticket:v1 SDO-9 · Fix login", workspace_id="w1"),
        Tab("t2", "ticket:v1 SDO-9 · Fix login", workspace_id="w1"),
    ]
    assert plan_recovery(_pending("tab_creating"), [], tabs) == Prompt([], tabs)


def test_tab_in_another_workspace_is_not_adopted():
    tabs = [Tab("t1", "ticket:v1 SDO-9 · Fix login", workspace_id="w2")]
    assert plan_recovery(_pending("tab_creating"), [], tabs) == Prompt([], [])


def test_plan_never_returns_a_create_step():
    tabs = [Tab("t1", "ticket:v1 SDO-9 · Fix login", workspace_id="w1")]
    for stage in ["creating", "jira_created", "tab_creating", "tab_created"]:
        decision = plan_recovery(_pending(stage), [], tabs)
        if isinstance(decision, ResumeAt):
            assert decision.step in {"tab", "adopt", "report"}


# --- recover(): one interruption per stage, driven through fakes -------------

import pytest  # noqa: E402

from fakes import Crash, FakeHerdr, FakeJira, Interrupted  # noqa: E402
from ticket_core.state import StateStore  # noqa: E402
from ticket_core.transactions import Capture, create_ticket, recover  # noqa: E402

CAPTURE = Capture(workspace_id="w1", cwd="/work")
NOW = datetime(2026, 10, 9, 14, 10)


@pytest.fixture
def store(tmp_path):
    return StateStore(tmp_path / "session" / "state.json")


def _create_crashing_at(store, herdr, jira, at):
    with pytest.raises(Interrupted):
        create_ticket(
            store, herdr, jira, CAPTURE, "Fix login", project="SDO", issue_type="Task",
            assignee="acc-1", site="acme", now=NOW, checkpoint=Crash(at),
        )


def _bound(herdr, key):
    """(tab_id, tab) for every tab labelled with this key."""
    return [
        (tid, t) for tid, t in herdr.tabs.items()
        if t["label"].startswith(f"ticket:v1 {key} · ")
    ]


def test_creating_crash_prompts_with_no_candidates_and_discard_clears(store):
    herdr, jira = FakeHerdr(), FakeJira(keys=["SDO-9"])
    _create_crashing_at(store, herdr, jira, "creating")

    assert recover(store, herdr, jira, site="acme") == Prompt([], [])
    assert jira.creates == []
    assert recover(store, herdr, jira, site="acme", choice=("discard",)) is None
    assert store.read().pending is None


def test_jira_call_crash_shows_created_key_and_confirm_completes_once(store):
    herdr = FakeHerdr()
    jira = FakeJira(keys=["SDO-9"], search_results=[Issue("SDO-9", "Fix login")])
    _create_crashing_at(store, herdr, jira, "jira_call")

    assert recover(store, herdr, jira, site="acme") == Prompt([Issue("SDO-9", "Fix login")], [])
    jql, site = jira.searches[0]
    assert 'summary ~ "Fix login"' in jql and site == "acme"

    assert recover(store, herdr, jira, site="acme", choice=("confirm", "SDO-9")) is None
    assert len(jira.creates) == 1
    [(_, tab)] = _bound(herdr, "SDO-9")
    assert herdr.tokens == {tab["root"]: "SDO-9"}
    assert store.read().pending is None


def test_jira_created_crash_resumes_without_second_create(store):
    herdr, jira = FakeHerdr(), FakeJira(keys=["SDO-9"])
    _create_crashing_at(store, herdr, jira, "jira_created")

    assert recover(store, herdr, jira, site="acme") is None
    assert len(jira.creates) == 1
    assert len(_bound(herdr, "SDO-9")) == 1
    assert store.read().pending is None


def test_tab_creating_crash_offers_new_tab_when_none_matches(store):
    herdr, jira = FakeHerdr(), FakeJira(keys=["SDO-9"])
    _create_crashing_at(store, herdr, jira, "tab_creating")

    assert recover(store, herdr, jira, site="acme") == Prompt([], [])
    assert herdr.tabs == {}
    assert recover(store, herdr, jira, site="acme", choice=("new_tab",)) is None
    assert len(_bound(herdr, "SDO-9")) == 1
    assert len(jira.creates) == 1
    assert store.read().pending is None


def test_tab_call_crash_adopts_the_single_match_without_asking(store):
    herdr, jira = FakeHerdr(), FakeJira(keys=["SDO-9"])
    _create_crashing_at(store, herdr, jira, "tab_call")
    [(tab_id, tab)] = _bound(herdr, "SDO-9")

    assert recover(store, herdr, jira, site="acme") is None
    # Adoption has no root pane (herdr `tab get` omits it, D25): no token is reported
    # here, and reconcile reports it on every pane of the bound tab.
    assert not any(c[0] == "tab_get" for c in herdr.calls)
    assert herdr.tokens == {}
    assert len(herdr.tabs) == 1
    assert store.read().pending is None
    for change in reconcile(herdr.snapshot()):
        if change.value is None:
            herdr.clear_token(change.pane_id)
        else:
            herdr.report_token(change.pane_id, change.value)
    assert herdr.tokens == {tab["root"]: "SDO-9"}
    assert tab_id in herdr.tabs


def test_tab_created_crash_reports_token_and_clears(store):
    herdr, jira = FakeHerdr(), FakeJira(keys=["SDO-9"])
    _create_crashing_at(store, herdr, jira, "tab_created")
    [(_, tab)] = _bound(herdr, "SDO-9")
    assert herdr.tokens == {}

    assert recover(store, herdr, jira, site="acme") is None
    assert herdr.tokens == {tab["root"]: "SDO-9"}
    assert store.read().pending is None


def test_several_matches_in_workspace_ask_and_other_workspace_is_not_adopted(store):
    herdr, jira = FakeHerdr(), FakeJira(keys=["SDO-9"])
    _create_crashing_at(store, herdr, jira, "tab_creating")
    herdr.add_tab("ticket:v1 SDO-9 · Fix login", "w1")
    herdr.add_tab("ticket:v1 SDO-9 · Fix login", "w1")
    herdr.add_tab("ticket:v1 SDO-9 · Fix login", "w2")

    prompt = recover(store, herdr, jira, site="acme")
    assert isinstance(prompt, Prompt)
    assert sorted(t.workspace_id for t in prompt.tabs) == ["w1", "w1"]
    assert not any(c[0] == "tab_get" for c in herdr.calls)
