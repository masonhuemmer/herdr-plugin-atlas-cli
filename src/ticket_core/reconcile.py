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


TITLE_CAP = 80  # Herdr caps token values at 80 characters (research Q2)


@dataclass(frozen=True)
class TokenChange:
    pane_id: str
    value: str | None
    title: str | None = None


def reconcile(snapshot: Snapshot) -> list[TokenChange]:
    # One target per pane, so re-applying the result is harmless (idempotent).
    labels = {t.tab_id: t.label for t in snapshot.tabs}
    changes = []
    for pane in sorted(snapshot.panes, key=lambda p: p.pane_id):
        binding = parse_marker(labels.get(pane.tab_id, ""))
        if binding:
            changes.append(TokenChange(pane.pane_id, binding.key, binding.title[:TITLE_CAP]))
        else:
            changes.append(TokenChange(pane.pane_id, None))
    return changes
