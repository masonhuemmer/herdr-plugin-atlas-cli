"""Curses overlay for the status menu. Thin: the choice goes through status_menu.apply_status
via the `choose` callable. Drawing is manual and untested, as with the picker."""

import curses

from ticket_core.ui import ENTER, ESC, step

UNBOUND = "This tab is not bound to a ticket"


def run(key, choices, choose) -> int:
    """Show the menu for `key`, or the not-bound message when `key` is None."""
    return curses.wrapper(lambda scr: _StatusUi(scr, key, choices, choose).main())


class _StatusUi:
    def __init__(self, scr, key, choices, choose):
        self.scr = scr
        self.key = key
        self.choices = list(choices)
        self.choose = choose
        self.sel = 0
        self.msg = ""
        self.done = False

    def main(self) -> int:
        self.scr.timeout(50)
        curses.curs_set(0)
        while not self.done:
            self._draw()
            ch = self.scr.getch()
            if ch != -1:
                self._key(ch)
        return 0

    def _key(self, ch):
        if self.key is None:
            self.done = True  # any key closes the not-bound message
        elif ch == ESC:
            self.done = True
        elif ch in (curses.KEY_UP, curses.KEY_DOWN):
            self.sel = step(self.sel, ch, len(self.choices))
        elif ch in ENTER:
            try:
                self.choose(self.choices[self.sel])
            except Exception as e:  # Jira or herdr failure: show it and stay open
                self.msg = f"failed: {e}"
            else:
                self.done = True

    def _draw(self):
        scr = self.scr
        scr.erase()
        rows, _ = scr.getmaxyx()
        for i, line in enumerate(self._lines()[: rows - 2]):
            self._put(i, line)
        self._put(rows - 1, self.msg)
        scr.refresh()

    def _put(self, y, text):
        try:
            _, cols = self.scr.getmaxyx()
            self.scr.addnstr(y, 0, text, cols - 1)
        except curses.error:
            pass

    def _lines(self) -> list[str]:
        if self.key is None:
            return [UNBOUND, "", "Press any key"]
        out = [f"Status of {self.key}", ""]
        for i, status in enumerate(self.choices):
            mark = ">" if i == self.sel else " "
            out.append(f"{mark} {status}")
        return out + ["", "Up/Down choose, Enter moves the ticket, Esc cancel"]
