"""Jira through the atlas CLI. Every call passes --site."""

import json
import subprocess

from ticket_core.recovery import Issue

ATLAS = "/opt/homebrew/bin/atlas"


class AtlasError(Exception):
    pass


class AtlasJira:
    def __init__(self, run=subprocess.run, atlas: str = ATLAS):
        self.run = run
        self.atlas = atlas

    def _run(self, args: list[str]) -> str:
        proc = self.run(
            [self.atlas, "jira", *args], capture_output=True, text=True, check=False
        )
        if proc.returncode != 0:
            raise AtlasError(proc.stderr.strip() or f"atlas exited {proc.returncode}")
        return proc.stdout

    def search(self, jql: str, site: str) -> list[Issue]:
        out = json.loads(self._run(["search", "--jql", jql, "--site", site]))
        return [Issue(item["key"], item["summary"]) for item in out["items"]]

    def create(self, project, issue_type, summary, assignee, site, dry_run=False) -> str | None:
        """Return the new key. A dry run creates nothing and returns None."""
        args = ["create", "--project", project, "--type", issue_type, "--summary", summary,
                "--assignee", assignee, "--site", site]
        if dry_run:
            args.append("--dry-run")
        out = json.loads(self._run(args))
        if dry_run:
            return None
        if "key" not in out:
            raise AtlasError("atlas jira create output has no key")
        return out["key"]

    def comment(self, key, body, site, dry_run=False) -> None:
        args = ["comment", key, "--body", body, "--site", site]
        if dry_run:
            args.append("--dry-run")
        self._run(args)
