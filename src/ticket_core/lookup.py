"""Lookup state for the picker: debounce, sequence numbers, stale-result drop. Pure."""

from ticket_core.jql import build_jql

DEBOUNCE = 0.3  # seconds of no typing before a request (design item 1)
LIMIT = 50  # atlas returns at most 50 items per call, with no paging


class Lookup:
    def __init__(self):
        self.text = ""
        self.seq = 0  # bumped by every change of text; a result is kept only for the latest
        self.edited_at = None
        self.asked = None  # the seq last requested, or last seen as empty (no request)
        self.results = None  # None while searching, else a list of issues

    def type_text(self, text, now):
        if text == self.text:
            return
        self.text = text
        self.seq += 1
        self.edited_at = now
        self.results = None
        if build_jql(text) is None:
            self.results = []
            self.asked = self.seq  # empty input sends nothing and drops outstanding results

    def poll(self, now):
        """(seq, jql) when a request is due, else None."""
        if self.edited_at is None or self.asked == self.seq:
            return None
        if (now - self.edited_at).total_seconds() < DEBOUNCE:
            return None
        self.asked = self.seq
        return self.seq, build_jql(self.text)

    def deliver(self, seq, items) -> bool:
        if seq != self.seq:
            return False
        self.results = list(items)
        return True

    def status(self) -> str:
        if build_jql(self.text) is None:
            return ""
        if self.results is None:
            return "searching…"
        if len(self.results) >= LIMIT:
            return f"{LIMIT}+ matches — keep typing"
        if not self.results:
            return "no matches"
        return ""
