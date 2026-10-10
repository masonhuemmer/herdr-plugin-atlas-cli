"""Recovery rules for a pending record. Pure: no I/O, and never a create."""

from dataclasses import dataclass

from ticket_core.marker import parse_marker
from ticket_core.reconcile import Snapshot, Tab
from ticket_core.state import Pending


@dataclass(frozen=True)
class Issue:
    key: str
    summary: str


@dataclass(frozen=True)
class Prompt:
    """The user must choose. Discard is always offered on top of these choices."""

    issues: list[Issue]
    tabs: list[Tab]


@dataclass(frozen=True)
class ResumeAt:
    """Continue without asking. step is "tab", "adopt" (with tab_id) or "report"."""

    step: str
    tab_id: str | None = None


def plan_recovery(pending: Pending, candidates: list[Issue], snap: Snapshot) -> Prompt | ResumeAt:
    if pending.stage == "creating":
        return Prompt(list(candidates), [])
    if pending.stage == "jira_created":
        return ResumeAt("tab")
    if pending.stage == "tab_creating":
        # The tab is labelled with the plain title; it is ours only if no pane is bound yet.
        title = parse_marker(pending.tab_label).title
        bound = {p.tab_id for p in snap.panes if parse_marker(p.label)}
        matches = [
            t for t in snap.tabs
            if t.label == title and t.workspace_id == pending.workspace_id and t.tab_id not in bound
        ]
        if len(matches) == 1:
            return ResumeAt("adopt", matches[0].tab_id)
        return Prompt([], matches)
    if pending.stage == "tab_created":
        return ResumeAt("report")
    raise ValueError(f"unknown stage: {pending.stage}")
