import pytest

from fakes import FakeHerdr
from ticket_core.adapters.herdr import HerdrError
from ticket_core.reconcile import Pane, Snapshot, Tab
from ticket_core.sync import snapshot_with_retry, sync_tokens


class Scripted:
    """Returns each scripted snapshot (or raises each scripted error) in order."""

    def __init__(self, *steps):
        self.steps = list(steps)
        self.calls = 0

    def snapshot(self):
        self.calls += 1
        step = self.steps.pop(0) if len(self.steps) > 1 else self.steps[0]
        if isinstance(step, Exception):
            raise step
        return step


def _empty():
    return Snapshot(tabs=[], panes=[])


def _one_tab():
    return Snapshot(tabs=[Tab("t1", "plain", "w1")], panes=[Pane("p1", "t1")])


def test_retry_waits_until_a_tab_appears():
    sleeps = []
    herdr = Scripted(_empty(), _empty(), _one_tab())
    snap = snapshot_with_retry(herdr, sleep=sleeps.append)
    assert snap.tabs and herdr.calls == 3
    assert sleeps == [0.5, 0.5]


def test_retry_is_bounded_at_twenty_attempts():
    sleeps = []
    herdr = Scripted(_empty())
    snap = snapshot_with_retry(herdr, sleep=sleeps.append)
    assert snap.tabs == [] and herdr.calls == 20
    assert len(sleeps) == 19


def test_retry_survives_a_failed_attempt():
    herdr = Scripted(HerdrError("not up yet"), _one_tab())
    assert snapshot_with_retry(herdr, sleep=lambda s: None).tabs


def test_retry_raises_when_every_attempt_fails():
    herdr = Scripted(HerdrError("down"))
    with pytest.raises(HerdrError):
        snapshot_with_retry(herdr, sleep=lambda s: None)


def test_sync_sets_tokens_for_bound_tabs_and_clears_the_rest():
    herdr = FakeHerdr()
    bound, root_b = herdr.add_tab("Fix login", "w1", pane_label="ticket:v1 EX-5 · Fix login")
    plain, root_p = herdr.add_tab("plain", "w1")
    herdr.tokens[root_p] = "EX-1"  # stale token from an earlier binding
    sync_tokens(herdr, sleep=lambda s: None)
    assert herdr.tokens == {root_b: "EX-5"}


def test_sync_clears_the_token_after_a_rename():
    herdr = FakeHerdr()
    tab, root = herdr.add_tab("Fix login", "w1", pane_label="ticket:v1 EX-5 · Fix login")
    sync_tokens(herdr, sleep=lambda s: None)
    herdr.pane_rename(root, "renamed")
    sync_tokens(herdr, sleep=lambda s: None)
    assert herdr.tokens == {}
