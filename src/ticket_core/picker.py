"""Picker actions. Each one is a transaction (or a Skip), then a token sync. The curses
screens in ui.py call these; they hold no logic of their own."""

import json
import os
import time
from pathlib import Path

from ticket_core.recovery import Issue, Prompt
from ticket_core.state import StateStore
from ticket_core.sync import sync_tokens
from ticket_core.transactions import Capture, create_ticket, lookup_bind, recover

CAPTURE_FILE = "capture.json"
CRASH_ENV = "HERDR_TICKET_CRASH_AT"  # D19: manual recovery tests only
CRASH_EXIT = 75


def write_capture(directory, workspace_id: str, cwd: str) -> None:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / CAPTURE_FILE).write_text(json.dumps({"workspace_id": workspace_id, "cwd": cwd}))


def read_capture(directory) -> Capture:
    raw = json.loads((Path(directory) / CAPTURE_FILE).read_text())
    return Capture(raw["workspace_id"], raw["cwd"])


def crash_checkpoint(env, exit=os._exit):
    """Exit with status 75 right after the named checkpoint, when HERDR_TICKET_CRASH_AT is set."""
    at = env.get(CRASH_ENV)

    def checkpoint(name: str) -> None:
        if at and name == at:
            exit(CRASH_EXIT)

    return checkpoint


def _no_checkpoint(name: str) -> None:
    pass


class Picker:
    def __init__(self, *, store: StateStore, herdr, jira, site, project, issue_type, assignee,
                 capture: Capture, now, checkpoint=_no_checkpoint, sleep=time.sleep):
        self.store = store
        self.herdr = herdr
        self.jira = jira
        self.site = site
        self.project = project
        self.issue_type = issue_type
        self.assignee = assignee
        self.capture = capture
        self.now = now
        self.checkpoint = checkpoint
        self.sleep = sleep

    def pending_stage(self) -> str | None:
        pending = self.store.read().pending
        return pending.stage if pending else None

    def start(self) -> Prompt | None:
        """Resume what can resume. Returns a Prompt when the user must choose."""
        prompt = recover(self.store, self.herdr, self.jira, site=self.site,
                         checkpoint=self.checkpoint)
        if prompt is None:
            sync_tokens(self.herdr, sleep=self.sleep)
        return prompt

    def answer(self, choice: tuple) -> None:
        recover(self.store, self.herdr, self.jira, site=self.site, choice=choice,
                checkpoint=self.checkpoint)
        sync_tokens(self.herdr, sleep=self.sleep)

    def search(self, jql: str) -> list[Issue]:
        return self.jira.search(jql, self.site)

    def bind(self, issue: Issue) -> None:
        lookup_bind(self.store, self.herdr, self.capture, issue.key, issue.summary, self.site,
                    checkpoint=self.checkpoint)
        sync_tokens(self.herdr, sleep=self.sleep)

    def create(self, description: str) -> None:
        create_ticket(self.store, self.herdr, self.jira, self.capture, description,
                      project=self.project, issue_type=self.issue_type, assignee=self.assignee,
                      site=self.site, now=self.now(), checkpoint=self.checkpoint)
        sync_tokens(self.herdr, sleep=self.sleep)

    def skip(self) -> None:
        self.herdr.tab_create(self.capture.workspace_id, self.capture.cwd)
