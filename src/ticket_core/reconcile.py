"""Work out each pane's ticket token from the snapshot. Pure: no I/O."""

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


@dataclass(frozen=True)
class Snapshot:
    tabs: list[Tab]
    panes: list[Pane]


@dataclass(frozen=True)
class TokenChange:
    pane_id: str
    value: str | None


def reconcile(snapshot: Snapshot) -> list[TokenChange]:
    # One target per pane, so re-applying the result is harmless (idempotent).
    labels = {t.tab_id: t.label for t in snapshot.tabs}
    changes = []
    for pane in sorted(snapshot.panes, key=lambda p: p.pane_id):
        binding = parse_marker(labels.get(pane.tab_id, ""))
        changes.append(TokenChange(pane.pane_id, binding.key if binding else None))
    return changes
