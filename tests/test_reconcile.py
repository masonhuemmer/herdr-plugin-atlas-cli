from ticket_core.reconcile import Pane, Snapshot, Tab, TokenChange, reconcile


def _snap(tabs, panes):
    return Snapshot(tabs=tabs, panes=panes)


def test_panes_in_bound_tab_get_key():
    snap = _snap(
        [Tab("t1", "ticket:v1 SDO-1 · Login")],
        [Pane("p1", "t1")],
    )
    assert reconcile(snap) == [TokenChange("p1", "SDO-1")]


def test_both_panes_of_a_split_bound_tab_get_key():
    snap = _snap(
        [Tab("t1", "ticket:v1 SDO-1 · Login")],
        [Pane("p1", "t1"), Pane("p2", "t1")],
    )
    assert reconcile(snap) == [TokenChange("p1", "SDO-1"), TokenChange("p2", "SDO-1")]


def test_unbound_and_plain_named_tabs_get_none():
    snap = _snap(
        [Tab("t1", "shell"), Tab("t2", "SDO-9")],
        [Pane("p1", "t1"), Pane("p2", "t2")],
    )
    assert reconcile(snap) == [TokenChange("p1", None), TokenChange("p2", None)]


def test_pane_with_unknown_tab_gets_none():
    snap = _snap([Tab("t1", "ticket:v1 SDO-1 · Login")], [Pane("p1", "gone")])
    assert reconcile(snap) == [TokenChange("p1", None)]


def test_reconcile_is_repeatable():
    snap = _snap(
        [Tab("t1", "ticket:v1 SDO-1 · Login")],
        [Pane("p2", "t1"), Pane("p1", "t1")],
    )
    first = reconcile(snap)
    assert first == reconcile(snap)
    assert [c.pane_id for c in first] == ["p1", "p2"]
