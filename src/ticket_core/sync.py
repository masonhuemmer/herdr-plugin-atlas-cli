"""Token sync: read the snapshot (bounded retry, D18) and make each pane's token match its tab."""

import time

from ticket_core.adapters.herdr import HerdrError
from ticket_core.reconcile import Snapshot, reconcile

ATTEMPTS = 20
DELAY = 0.5  # seconds between attempts; placeholder until measured in M9


def snapshot_with_retry(herdr, *, attempts=ATTEMPTS, delay=DELAY, sleep=time.sleep) -> Snapshot:
    """Snapshot until it has a tab, at most `attempts` times. Raises only if every attempt failed."""
    snap, error = None, None
    for attempt in range(attempts):
        if attempt:
            sleep(delay)
        try:
            snap = herdr.snapshot()
        except HerdrError as e:
            error = e
            continue
        if snap.tabs:
            return snap
    if snap is None:
        raise error
    return snap


def apply_tokens(herdr, snap: Snapshot) -> None:
    for change in reconcile(snap):
        if change.value is None:
            herdr.clear_token(change.pane_id)
        else:
            herdr.report_token(change.pane_id, change.value, change.title)


def sync_tokens(herdr, *, sleep=time.sleep) -> None:
    apply_tokens(herdr, snapshot_with_retry(herdr, sleep=sleep))
