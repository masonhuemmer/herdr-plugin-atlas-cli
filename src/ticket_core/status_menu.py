"""Status menu logic: is the tab bound, what a choice does, and the capture of the pane it was
opened from. Pure apart from the files it is given; the curses screen lives in status_ui.py."""

import json
import time
from pathlib import Path

from ticket_core.marker import Binding, parse_marker
from ticket_core.reconcile import Snapshot
from ticket_core.sync import sync_tokens

CAPTURE_FILE = "status_capture.json"


def write_status_capture(directory, pane_id: str) -> None:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / CAPTURE_FILE).write_text(json.dumps({"pane_id": pane_id}))


def read_status_capture(directory) -> str:
    return json.loads((Path(directory) / CAPTURE_FILE).read_text())["pane_id"]


def bound_binding(snapshot: Snapshot, pane_id: str) -> Binding | None:
    """The ticket the pane's own label binds it to, or None when it is not bound."""
    for pane in snapshot.panes:
        if pane.pane_id == pane_id:
            return parse_marker(pane.label)
    return None


def invalidate_status(cache_path, key: str) -> None:
    """Drop one key from the session status cache so the next fetch asks Jira again."""
    from ticket_core.sync import load_cache, write_cache

    cache = load_cache(cache_path)
    cache.pop(key, None)
    write_cache(cache_path, cache)  # also repairs an unreadable cache


def apply_status(key: str, status: str, *, jira, herdr, site, cache_path, sleep=time.sleep,
                 now=time.time) -> None:
    """Move the ticket to `status`, then refresh its cached status and the sidebar row.

    A failed transition raises before anything else changes."""
    jira.transition(key, status, site)
    invalidate_status(cache_path, key)
    sync_tokens(herdr, jira=jira, site=site, cache_path=cache_path, sleep=sleep, now=now)
