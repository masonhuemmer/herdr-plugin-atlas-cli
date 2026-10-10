"""Token sync: read the snapshot (bounded retry, D18), fetch statuses (cached), and make each pane's tokens match its tab."""

import json
import time
from pathlib import Path

from ticket_core.adapters.herdr import HerdrError
from ticket_core.reconcile import Snapshot, bound_keys, reconcile

ATTEMPTS = 20
DELAY = 0.5  # seconds between attempts; placeholder until measured in M9
STATUS_TTL = 300  # seconds a fetched status is reused; reconcile runs on every pane creation


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


def fetch_statuses(snap: Snapshot, jira, site, cache_path: Path | None, *, now=time.time,
                   ttl=STATUS_TTL) -> dict[str, str]:
    """Status per bound key. Reuses a cached value within `ttl`; a failed lookup is left out."""
    from ticket_core.adapters.jira import AtlasError

    cache = {}
    if cache_path and cache_path.exists():
        cache = json.loads(cache_path.read_text())
    statuses, dirty = {}, False
    for key in sorted(bound_keys(snap)):
        entry = cache.get(key)
        if entry and now() - entry["at"] < ttl:
            statuses[key] = entry["status"]
            continue
        try:
            status = jira.status(key, site)
        except AtlasError:
            continue
        if status:
            statuses[key] = status
            cache[key] = {"status": status, "at": now()}
            dirty = True
    if cache_path and dirty:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(cache, indent=2))
    return statuses


def apply_tokens(herdr, changes) -> None:
    for change in changes:
        if change.value is None:
            herdr.clear_token(change.pane_id)
        else:
            herdr.report_token(change.pane_id, change.value, change.status)


def sync_tokens(herdr, *, jira=None, site=None, cache_path=None, sleep=time.sleep,
                now=time.time) -> None:
    snap = snapshot_with_retry(herdr, sleep=sleep)
    statuses = fetch_statuses(snap, jira, site, cache_path, now=now) if jira and site else {}
    apply_tokens(herdr, reconcile(snap, statuses))
