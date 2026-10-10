"""Binding marker: the versioned label that links a Herdr tab to a Jira key."""

import re
from dataclasses import dataclass

_MARKER = re.compile(r"ticket:v1 ([A-Z][A-Z0-9]+-[0-9]+) · (.+)")


@dataclass(frozen=True)
class Binding:
    key: str
    title: str


def parse_marker(label: str) -> Binding | None:
    m = _MARKER.fullmatch(label)
    return Binding(m[1], m[2]) if m else None


def format_marker(key: str, title: str) -> str:
    return f"ticket:v1 {key} · {title}"
