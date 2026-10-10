from datetime import datetime

import pytest

from ticket_core.state import Busy, Pending, State, StateStore


def test_missing_file_reads_as_empty(tmp_path):
    store = StateStore(tmp_path / "state.json")
    assert store.read() == State(site=None, pending=None)


def test_write_then_read_round_trips_pending(tmp_path):
    store = StateStore(tmp_path / "state.json")
    pending = Pending(
        stage="creating",
        started_at=datetime(2026, 10, 9, 14, 10),
        description="Fix login",
        key=None,
        workspace_id="w1",
        cwd="/work",
        tab_label=None,
        tab_id=None,
        root_pane_id=None,
    )
    store.write(State(site="acme", pending=pending))
    assert store.read() == State(site="acme", pending=pending)


def test_lock_refuses_second_holder_without_queueing(tmp_path):
    path = tmp_path / "state.json"
    with StateStore(path).lock():
        with pytest.raises(Busy):
            with StateStore(path).lock():
                pass
    with StateStore(path).lock():
        pass
