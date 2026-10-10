"""Transactions: each one holds the state lock for its whole run, checks and writes
the pending record, and calls the Jira and Herdr adapters it is given."""

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Callable, Protocol

from ticket_core.jql import build_recovery_jql, normalise
from ticket_core.marker import format_marker, parse_marker
from ticket_core.recovery import Issue, Prompt, ResumeAt, plan_recovery
from ticket_core.reconcile import Snapshot
from ticket_core.state import Pending, State, StateStore

# Each name is a point where a write has just happened (or a call is about to start).
# The picker's crash hook (D19) passes a checkpoint that exits at one of these.
CHECKPOINTS = ("creating", "jira_call", "jira_created", "tab_creating", "tab_call", "tab_created")

Checkpoint = Callable[[str], None]


def _no_checkpoint(name: str) -> None:
    pass


class Refused(Exception):
    """The request is not allowed right now (empty text, or a pending record exists)."""


@dataclass(frozen=True)
class Capture:
    workspace_id: str
    cwd: str


class Jira(Protocol):
    def search(self, jql: str, site: str) -> list[Issue]: ...

    def create(self, project: str, issue_type: str, summary: str, assignee: str, site: str) -> str: ...

    def transition(self, key: str, status: str, site: str) -> None: ...


class HerdrLike(Protocol):
    def snapshot(self) -> Snapshot: ...

    def tab_create(self, workspace_id: str, cwd: str, label: str | None = None) -> tuple[str, str]: ...

    def pane_rename(self, pane_id: str, label: str) -> None: ...

    def report_token(self, pane_id: str, key: str) -> None: ...

    def clear_token(self, pane_id: str) -> None: ...

    def clear_label(self, pane_id: str) -> None: ...


def _write(store: StateStore, site: str | None, pending: Pending | None) -> None:
    store.write(State(site=site, pending=pending))


def _make_tab(store, herdr, site, pending, checkpoint):
    pending = replace(pending, stage="tab_creating")
    _write(store, site, pending)
    checkpoint("tab_creating")
    # The tab shows the plain title; the binding marker goes on its root pane.
    title = parse_marker(pending.tab_label).title
    tab_id, root = herdr.tab_create(pending.workspace_id, pending.cwd, label=title)
    checkpoint("tab_call")
    herdr.pane_rename(root, pending.tab_label)
    _finish_tab(store, herdr, site, replace(pending, tab_id=tab_id, root_pane_id=root), checkpoint)


def _adopt(store, herdr, site, pending, tab_id, snap, checkpoint):
    # Bind the adopted tab by labelling its lowest pane id (the tab has no root pane we know).
    pane_id = min(p.pane_id for p in snap.panes if p.tab_id == tab_id)
    herdr.pane_rename(pane_id, pending.tab_label)
    _finish_tab(store, herdr, site, replace(pending, tab_id=tab_id), checkpoint)


def _finish_tab(store, herdr, site, pending, checkpoint):
    pending = replace(pending, stage="tab_created")
    _write(store, site, pending)
    checkpoint("tab_created")
    if pending.root_pane_id is not None:
        herdr.report_token(pending.root_pane_id, pending.key)
    # An adopted tab has no root pane (D25); reconcile reports its token instead.
    _write(store, site, None)  # clears pending and records the site


def _start_work(jira, key, site) -> None:
    # Best effort: a failed move leaves the ticket To Do; the create still stands.
    try:
        jira.transition(key, "In Progress", site)
    except Exception:
        pass


def _after_jira(store, herdr, site, pending, checkpoint):
    pending = replace(pending, stage="jira_created", tab_label=format_marker(pending.key, pending.description))
    _write(store, site, pending)
    checkpoint("jira_created")
    _make_tab(store, herdr, site, pending, checkpoint)


def lookup_bind(
    store: StateStore,
    herdr: HerdrLike,
    capture: Capture,
    key: str,
    title: str,
    site: str,
    *,
    checkpoint: Checkpoint = _no_checkpoint,
) -> None:
    with store.lock():
        if store.read().pending is not None:
            raise Refused("a pending record exists")
        pending = Pending(
            stage="tab_creating",
            started_at=None,
            description=None,
            key=key,
            workspace_id=capture.workspace_id,
            cwd=capture.cwd,
            tab_label=format_marker(key, title),
            tab_id=None,
            root_pane_id=None,
        )
        _make_tab(store, herdr, site, pending, checkpoint)


def create_ticket(
    store: StateStore,
    herdr: HerdrLike,
    jira: Jira,
    capture: Capture,
    description: str,
    *,
    project: str,
    issue_type: str,
    assignee: str,
    site: str,
    now: datetime,
    checkpoint: Checkpoint = _no_checkpoint,
) -> None:
    text = normalise(description)
    if not text:
        raise Refused("description is empty")
    with store.lock():
        if store.read().pending is not None:
            raise Refused("a pending record exists")
        pending = Pending(
            stage="creating",
            started_at=now,
            description=text,
            key=None,
            workspace_id=capture.workspace_id,
            cwd=capture.cwd,
            tab_label=None,
            tab_id=None,
            root_pane_id=None,
        )
        _write(store, site, pending)
        checkpoint("creating")
        key = jira.create(project=project, issue_type=issue_type, summary=text,
                          assignee=assignee, site=site)
        checkpoint("jira_call")
        _start_work(jira, key, site)
        _after_jira(store, herdr, site, replace(pending, key=key), checkpoint)


def discard(store: StateStore) -> None:
    with store.lock():
        state = store.read()
        _write(store, state.site, None)


def apply_site_change(store: StateStore, herdr: HerdrLike, site: str) -> None:
    with store.lock():
        state = store.read()
        if state.site == site:
            return
        pending = state.pending
        if state.site is not None:
            # Site change (Decision 8): unbind every bound pane, then drop pending.
            for pane in herdr.snapshot().panes:
                if parse_marker(pane.label) is None:
                    continue
                herdr.clear_label(pane.pane_id)
                herdr.clear_token(pane.pane_id)
            pending = None
        _write(store, site, pending)


def _resume(store, herdr, site, pending, decision, snap, checkpoint):
    if decision.step == "tab":
        _make_tab(store, herdr, site, pending, checkpoint)
    elif decision.step == "adopt":
        _adopt(store, herdr, site, pending, decision.tab_id, snap, checkpoint)
    else:  # "report"
        _finish_tab(store, herdr, site, pending, checkpoint)


def _apply_choice(store, herdr, site, pending, choice, snap, checkpoint):
    kind = choice[0]
    if kind == "discard":
        _write(store, site, None)
    elif kind == "confirm" and pending.stage == "creating":
        _after_jira(store, herdr, site, replace(pending, key=choice[1]), checkpoint)
    elif kind == "adopt" and pending.stage == "tab_creating":
        _adopt(store, herdr, site, pending, choice[1], snap, checkpoint)
    elif kind == "new_tab" and pending.stage == "tab_creating":
        _make_tab(store, herdr, site, pending, checkpoint)
    else:
        raise ValueError(f"choice {choice!r} does not fit stage {pending.stage}")


def recover(
    store: StateStore,
    herdr: HerdrLike,
    jira: Jira,
    *,
    site: str,
    choice: tuple | None = None,
    checkpoint: Checkpoint = _no_checkpoint,
) -> Prompt | None:
    """Resume or ask. Returns a Prompt when the user must choose (call again with `choice`),
    or None when nothing is pending or the record was finished or resumed without a prompt."""
    with store.lock():
        pending = store.read().pending
        if pending is None:
            return None
        issues, snap = [], Snapshot(tabs=[], panes=[])
        if pending.stage == "creating":
            issues = jira.search(build_recovery_jql(pending.description, pending.started_at), site)
        elif pending.stage == "tab_creating":
            snap = herdr.snapshot()
        decision = plan_recovery(pending, issues, snap)
        if isinstance(decision, ResumeAt):
            _resume(store, herdr, site, pending, decision, snap, checkpoint)
            return None
        if choice is None:
            return decision
        _apply_choice(store, herdr, site, pending, choice, snap, checkpoint)
        return None
