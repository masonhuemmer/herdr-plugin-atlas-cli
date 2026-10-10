import pytest

from fake_run import FakeRun, fixture_json, fixture_text
from ticket_core.adapters.herdr import HerdrAdapter, HerdrError

HERDR = "/Users/mason/.local/bin/herdr"


def _herdr(run):
    return HerdrAdapter(run=run, herdr=HERDR)


def test_snapshot_fixture_maps_tabs_and_panes():
    run = FakeRun(stdout=fixture_text("herdr_snapshot.json"))
    snap = _herdr(run).snapshot()
    assert run.argv == [[HERDR, "api", "snapshot"]]
    tab = next(t for t in snap.tabs if t.tab_id == "w7:t7")
    assert tab.workspace_id == "w7"
    assert any(p.pane_id == "w7:p7" and p.tab_id == "w7:t7" for p in snap.panes)
    recorded = fixture_json("herdr_snapshot.json")["result"]["snapshot"]
    assert len(snap.tabs) == len(recorded["tabs"])
    assert len(snap.panes) == len(recorded["panes"])


def test_snapshot_nonzero_exit_raises():
    with pytest.raises(HerdrError):
        _herdr(FakeRun(stderr="no socket", returncode=1)).snapshot()


def test_tab_create_argv_focuses_and_omits_label_when_none():
    run = FakeRun(stdout=fixture_text("herdr_tab_create.json"))
    tab_id, root = _herdr(run).tab_create("w8", "/work/repo")
    assert run.argv == [[HERDR, "tab", "create", "--workspace", "w8", "--cwd", "/work/repo",
                         "--focus"]]
    assert (tab_id, root) == ("w0:t0", "w0:p0")


def test_tab_create_argv_includes_label_when_given():
    run = FakeRun(stdout=fixture_text("herdr_tab_create.json"))
    _herdr(run).tab_create("w8", "/work/repo", label="ticket:v1 SDO-1 · Fix")
    assert "--focus" in run.argv[0]
    assert run.argv[0][run.argv[0].index("--label") + 1] == "ticket:v1 SDO-1 · Fix"


def test_report_token_argv():
    run = FakeRun()
    _herdr(run).report_token("w8:p3", "SDO-1")
    assert run.argv == [[HERDR, "pane", "report-metadata", "w8:p3", "--source", "herdr-ticket",
                         "--token", "ticket=SDO-1"]]


def test_clear_token_argv():
    run = FakeRun()
    _herdr(run).clear_token("w8:p3")
    assert run.argv == [[HERDR, "pane", "report-metadata", "w8:p3", "--source", "herdr-ticket",
                         "--clear-token", "ticket", "--clear-token", "ticket_title"]]


def test_report_token_argv_carries_key_and_title():
    run = FakeRun()
    _herdr(run).report_token("w8:p3", "SDO-5", "Fix login")
    assert run.argv == [[HERDR, "pane", "report-metadata", "w8:p3", "--source", "herdr-ticket",
                         "--token", "ticket=SDO-5", "--token", "ticket_title=Fix login"]]
