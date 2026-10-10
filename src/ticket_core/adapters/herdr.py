"""Herdr through its CLI. Results are the `result` object of the CLI's JSON envelope."""

import json
import os
import subprocess

from ticket_core.reconcile import Pane, Snapshot, Tab

DEFAULT_HERDR = "/Users/mason/.local/bin/herdr"
SOURCE = "herdr-ticket"
TOKEN = "ticket"
STATUS_TOKEN = "ticket_status"


class HerdrError(Exception):
    pass


class HerdrAdapter:
    def __init__(self, run=subprocess.run, herdr: str | None = None):
        self.run = run
        self.herdr = herdr or os.environ.get("HERDR_BIN_PATH") or DEFAULT_HERDR

    def _run(self, args: list[str]) -> str:
        proc = self.run(
            [self.herdr, *args], capture_output=True, text=True, check=False
        )
        if proc.returncode != 0:
            raise HerdrError(proc.stderr.strip() or f"herdr exited {proc.returncode}")
        return proc.stdout

    def snapshot(self) -> Snapshot:
        snap = json.loads(self._run(["api", "snapshot"]))["result"]["snapshot"]
        return Snapshot(
            tabs=[Tab(t["tab_id"], t["label"], t["workspace_id"]) for t in snap["tabs"]],
            panes=[Pane(p["pane_id"], p["tab_id"]) for p in snap["panes"]],
        )

    def tab_create(self, workspace_id, cwd, label=None) -> tuple[str, str]:
        args = ["tab", "create", "--workspace", workspace_id, "--cwd", cwd]
        if label is not None:
            args += ["--label", label]
        args.append("--focus")
        result = json.loads(self._run(args))["result"]
        return result["tab"]["tab_id"], result["root_pane"]["pane_id"]

    def tab_rename(self, tab_id, label) -> None:
        self._run(["tab", "rename", tab_id, label])

    def report_token(self, pane_id, key, status=None) -> None:
        args = ["pane", "report-metadata", pane_id, "--source", SOURCE, "--token", f"{TOKEN}={key}"]
        if status:
            args += ["--token", f"{STATUS_TOKEN}={status}"]
        self._run(args)

    def clear_token(self, pane_id) -> None:
        self._run(["pane", "report-metadata", pane_id, "--source", SOURCE,
                    "--clear-token", TOKEN, "--clear-token", STATUS_TOKEN])
