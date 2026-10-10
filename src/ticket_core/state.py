"""Per-session state file and its lock. The only module here that touches the disk."""

import fcntl
import json
import os
import tempfile
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path


class Busy(Exception):
    """Another transaction holds the state lock. Callers refuse; they do not queue."""


@dataclass(frozen=True)
class Pending:
    stage: str
    started_at: datetime | None
    description: str | None
    key: str | None
    workspace_id: str
    cwd: str
    tab_label: str | None
    tab_id: str | None
    root_pane_id: str | None


@dataclass(frozen=True)
class State:
    site: str | None
    pending: Pending | None


class StateStore:
    def __init__(self, path: Path):
        self.path = Path(path)

    @contextmanager
    def lock(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path.with_suffix(".lock"), os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            raise Busy(str(self.path)) from None
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def read(self) -> State:
        try:
            raw = json.loads(self.path.read_text())
        except FileNotFoundError:
            return State(site=None, pending=None)
        p = raw["pending"]
        pending = None
        if p is not None:
            started = p["started_at"]
            pending = Pending(
                **{**p, "started_at": datetime.fromisoformat(started) if started else None}
            )
        return State(site=raw["site"], pending=pending)

    def write(self, state: State) -> None:
        pending = None
        if state.pending is not None:
            pending = asdict(state.pending)
            started = state.pending.started_at
            pending["started_at"] = started.isoformat() if started else None
        data = json.dumps({"site": state.site, "pending": pending}, indent=2)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".state-", suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)
