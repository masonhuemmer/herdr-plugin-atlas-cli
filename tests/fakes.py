"""In-memory stand-ins for the Jira and Herdr adapters, plus a crash checkpoint."""

import threading

from ticket_core.recovery import Issue
from ticket_core.reconcile import Pane, Snapshot, Tab
from ticket_core.transactions import CHECKPOINTS


class Interrupted(Exception):
    pass


class Crash:
    """A checkpoint that interrupts the flow when it reaches `name`."""

    def __init__(self, name: str):
        assert name in CHECKPOINTS, name
        self.name = name
        self.seen: list[str] = []

    def __call__(self, name: str) -> None:
        self.seen.append(name)
        if name == self.name:
            raise Interrupted(name)


class FakeJira:
    def __init__(self, keys=(), search_results=(), fail_on_create=False, gate=None, log=None):
        self.keys = list(keys)
        self.search_results = list(search_results)
        self.fail_on_create = fail_on_create
        self.gate = gate  # threading.Event: create blocks on it after `entered` is set
        self.entered = threading.Event()
        self.creates: list[dict] = []
        self.searches: list[tuple[str, str]] = []
        self.log = [] if log is None else log

    def search(self, jql: str, site: str) -> list[Issue]:
        self.searches.append((jql, site))
        return list(self.search_results)

    def create(self, project, issue_type, summary, assignee, site) -> str:
        self.creates.append(
            dict(project=project, issue_type=issue_type, summary=summary,
                 assignee=assignee, site=site)
        )
        self.log.append("jira.create")
        self.entered.set()
        if self.gate is not None:
            self.gate.wait(5)
        if self.fail_on_create:
            raise RuntimeError("atlas failed")
        return self.keys.pop(0)


class FakeHerdr:
    def __init__(self, log=None):
        self.tabs: dict[str, dict] = {}  # tab_id -> {label, workspace_id, root}
        self.panes: dict[str, str] = {}  # pane_id -> tab_id
        self.tokens: dict[str, str] = {}  # pane_id -> key
        self.titles: dict[str, str | None] = {}  # pane_id -> title
        self.calls = [] if log is None else log  # shared call log, in order
        self._n = 0

    def _new_id(self, prefix: str) -> str:
        self._n += 1
        return f"{prefix}{self._n}"

    def add_tab(self, label: str, workspace_id: str) -> tuple[str, str]:
        tab_id, pane_id = self._new_id("t"), self._new_id("p")
        self.tabs[tab_id] = {"label": label, "workspace_id": workspace_id, "root": pane_id}
        self.panes[pane_id] = tab_id
        return tab_id, pane_id

    def snapshot(self) -> Snapshot:
        return Snapshot(
            tabs=[Tab(t, v["label"], v["workspace_id"]) for t, v in self.tabs.items()],
            panes=[Pane(p, t) for p, t in self.panes.items()],
        )

    def tab_create(self, workspace_id, cwd, label=None):
        self.calls.append(("tab_create", workspace_id, cwd, label))
        return self.add_tab(label or "", workspace_id)

    def tab_rename(self, tab_id, label):
        self.calls.append(("tab_rename", tab_id, label))
        self.tabs[tab_id]["label"] = label

    def report_token(self, pane_id, key, title=None):
        self.calls.append(("report_token", pane_id, key))
        self.titles[pane_id] = title
        self.tokens[pane_id] = key

    def clear_token(self, pane_id):
        self.calls.append(("clear_token", pane_id))
        self.tokens.pop(pane_id, None)
        self.titles.pop(pane_id, None)
