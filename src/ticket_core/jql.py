"""Turn user input into JQL. Pure: no I/O."""

import re
from datetime import datetime, timedelta

_KEY = re.compile(r"[A-Za-z][A-Za-z0-9]+-[0-9]+")


def normalise(text: str) -> str:
    # `*` and `?` are removed, never searched for, so they cannot act as wildcards.
    return text.replace("*", "").replace("?", "").strip()


def _escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def build_jql(text: str) -> str | None:
    n = normalise(text)
    if not n:
        return None
    if _KEY.fullmatch(n):
        return f'key = "{n.upper()}"'
    return f'summary ~ "{_escape(n)}*"'


def build_recovery_jql(description: str, started_at: datetime) -> str:
    since = (started_at - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M")
    return (
        f'reporter = currentUser() AND summary ~ "{_escape(description)}" '
        f'AND created >= "{since}"'
    )
