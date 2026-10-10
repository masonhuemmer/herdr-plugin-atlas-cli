"""Work out each pane's ticket token from the snapshot. Pure: no I/O.

A pane is bound when its own label holds the marker (the binding lives on the pane)."""

from dataclasses import dataclass

from ticket_core.marker import parse_marker


@dataclass(frozen=True)
class Tab:
    tab_id: str
    label: str
    # None when the caller does not know it (Phase 1 callers); recovery needs it.
    workspace_id: str | None = None


@dataclass(frozen=True)
class Pane:
    pane_id: str
    tab_id: str
    label: str = ""


@dataclass(frozen=True)
class Snapshot:
    tabs: list[Tab]
    panes: list[Pane]


@dataclass(frozen=True)
class TokenChange:
    pane_id: str
    value: str | None
    status: str | None = None


def bound_keys(snapshot: Snapshot) -> set[str]:
    return {b.key for b in (parse_marker(p.label) for p in snapshot.panes) if b}


def reconcile(snapshot: Snapshot, statuses: dict[str, str] | None = None) -> list[TokenChange]:
    # One target per pane, so re-applying the result is harmless (idempotent).
    statuses = statuses or {}
    changes = []
    for pane in sorted(snapshot.panes, key=lambda p: p.pane_id):
        binding = parse_marker(pane.label)
        if binding:
            changes.append(TokenChange(pane.pane_id, binding.key, statuses.get(binding.key)))
        else:
            changes.append(TokenChange(pane.pane_id, None))
    return changes
