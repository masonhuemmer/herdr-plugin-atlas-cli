"""Recovery rules for a pending record. Pure: no I/O, and never a create."""

from dataclasses import dataclass

from ticket_core.reconcile import Tab
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


def plan_recovery(pending: Pending, candidates: list[Issue], tabs: list[Tab]) -> Prompt | ResumeAt:
    if pending.stage == "creating":
        return Prompt(list(candidates), [])
    if pending.stage == "jira_created":
        return ResumeAt("tab")
    if pending.stage == "tab_creating":
        prefix = f"ticket:v1 {pending.key} · "
        matches = [
            t for t in tabs if t.label.startswith(prefix) and t.workspace_id == pending.workspace_id
        ]
        if len(matches) == 1:
            return ResumeAt("adopt", matches[0].tab_id)
        return Prompt([], matches)
    if pending.stage == "tab_created":
        return ResumeAt("report")
    raise ValueError(f"unknown stage: {pending.stage}")
