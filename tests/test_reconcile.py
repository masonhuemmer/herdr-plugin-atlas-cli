from ticket_core.reconcile import Pane, Snapshot, Tab, TokenChange, bound_keys, reconcile

MARKER = "ticket:v1 SDO-1 · Login"


def _snap(tabs, panes):
    return Snapshot(tabs=tabs, panes=panes)


def test_labelled_pane_gets_key():
    snap = _snap([Tab("t1", "Login")], [Pane("p1", "t1", MARKER)])
    assert reconcile(snap) == [TokenChange("p1", "SDO-1")]


def test_only_the_labelled_pane_of_a_split_tab_is_bound():
    snap = _snap(
        [Tab("t1", "Login")],
        [Pane("p1", "t1", MARKER), Pane("p2", "t1")],
    )
    assert reconcile(snap) == [TokenChange("p1", "SDO-1"), TokenChange("p2", None)]


def test_status_is_carried_for_the_bound_key():
    snap = _snap([Tab("t1", "Login")], [Pane("p1", "t1", MARKER)])
    assert reconcile(snap, {"SDO-1": "Done"}) == [TokenChange("p1", "SDO-1", "Done")]


def test_unlabelled_panes_and_plain_tab_names_get_none():
    snap = _snap(
        [Tab("t1", "shell"), Tab("t2", "SDO-9")],
        [Pane("p1", "t1"), Pane("p2", "t2")],
    )
    assert reconcile(snap) == [TokenChange("p1", None), TokenChange("p2", None)]


def test_old_marker_in_tab_label_is_not_a_binding():
    snap = _snap([Tab("t1", "ticket:v1 SDO-1 · Login")], [Pane("p1", "t1")])
    assert reconcile(snap) == [TokenChange("p1", None)]


def test_bound_keys_reads_pane_labels_not_tab_labels():
    snap = _snap(
        [Tab("t1", "ticket:v1 SDO-7 · Old"), Tab("t2", "Login")],
        [Pane("p1", "t1"), Pane("p2", "t2", MARKER)],
    )
    assert bound_keys(snap) == {"SDO-1"}


def test_reconcile_is_repeatable():
    snap = _snap(
        [Tab("t1", "Login")],
        [Pane("p2", "t1"), Pane("p1", "t1", MARKER)],
    )
    assert reconcile(snap) == reconcile(snap)
