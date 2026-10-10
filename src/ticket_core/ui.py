"""Curses screens for the picker overlay. Thin: every action goes through picker.Picker."""

import curses
import queue
import re
import threading
from datetime import datetime

from ticket_core.lookup import Lookup
from ticket_core.transactions import Refused

KEY_SHAPE = re.compile(r"[A-Za-z][A-Za-z0-9]+-[0-9]+")
ENTER = (10, 13, curses.KEY_ENTER)
BACKSPACE = (curses.KEY_BACKSPACE, 127, 8)
ESC = 27


def step(sel: int, ch: int, count: int) -> int:
    """Move a list selection one row up or down, clamped to the `count` rows."""
    if ch == curses.KEY_UP:
        return max(0, sel - 1)
    if ch == curses.KEY_DOWN:
        return min(max(0, count - 1), sel + 1)
    return sel


def run(picker) -> int:
    return curses.wrapper(lambda scr: _Ui(scr, picker).main())


class _Ui:
    def __init__(self, scr, picker):
        self.scr = scr
        self.p = picker
        self.mode = "menu"
        self.text = ""
        self.msg = ""
        self.lookup = Lookup()
        self.sel = 0
        self.options: list[tuple[str, tuple, str]] = []  # (label, choice, hint) for recovery
        self.recover_stage = None
        self.done = False
        self.answers = queue.Queue()

    def main(self) -> int:
        self.scr.timeout(50)
        curses.curs_set(0)
        try:
            prompt = self.p.start()
        except Exception as e:  # shown on screen; the pending record stays
            prompt, self.msg = None, f"recovery failed: {e}"
        if prompt is not None:
            self._recovery(prompt)
        while not self.done:
            self._pump()
            self._draw()
            ch = self.scr.getch()
            if ch != -1:
                self._key(ch)
        return 0

    def _recovery(self, prompt):
        stage = self.p.pending_stage()
        self.mode = "recover"
        self.options = []
        if stage == "creating":
            self.options = [(f"{i.key}  {i.summary}", ("confirm", i.key), "") for i in prompt.issues]
        else:
            self.options = [(f"{t.label}", ("adopt", t.tab_id), "") for t in prompt.tabs]
        self.recover_stage = stage

    def _try(self, fn):
        try:
            fn()
            return True
        except Refused as e:
            self.msg = f"refused: {e}"
        except Exception as e:  # atlas or herdr failure: show it, keep the state
            self.msg = f"failed: {e}"
        return False

    def _key(self, ch):
        if self.mode == "menu":
            if ch in (ord("l"), ord("L")):
                self.mode = "lookup"
            elif ch in (ord("c"), ord("C")):
                self.mode, self.text = "create", ""
            elif ch in (ord("s"), ord("S")):
                if self._try(self.p.skip):
                    self.done = True
            elif ch in (ord("q"), ESC):
                self.done = True
        elif self.mode == "lookup":
            self._key_lookup(ch)
        elif self.mode == "create":
            if ch == ESC:
                self.mode = "menu"
            elif ch in ENTER:
                self._try(lambda: self.p.create(self.text)) and self._finish()
            else:
                self.text = self._edit(self.text, ch)
        elif self.mode == "typed":
            if ch == ESC:
                self.mode = "recover"
            elif ch in ENTER:
                if KEY_SHAPE.fullmatch(self.text):
                    key = self.text.upper()
                    self._try(lambda: self.p.answer(("confirm", key))) and self._finish()
                else:
                    self.msg = "type a ticket key such as SDO-12"
            else:
                self.text = self._edit(self.text, ch)
        elif self.mode == "recover":
            self._key_recover(ch)

    def _key_lookup(self, ch):
        if ch == ESC:
            self.mode = "menu"
        elif ch in (curses.KEY_UP, curses.KEY_DOWN):
            self.sel = step(self.sel, ch, len(self.lookup.results or []))
        elif ch in ENTER:
            results = self.lookup.results or []
            if results and self.lookup.text.strip():
                issue = results[min(self.sel, len(results) - 1)]
                self._try(lambda: self.p.bind(issue)) and self._finish()
        else:
            self.text = self._edit(self.lookup.text, ch)
            self.lookup.type_text(self.text, datetime.now())
            self.sel = 0

    def _key_recover(self, ch):
        if ch == ord("d"):
            self._try(lambda: self.p.answer(("discard",))) and self._finish()
        elif ch == ord("n") and self.recover_stage == "tab_creating":
            self._try(lambda: self.p.answer(("new_tab",))) and self._finish()
        elif ch == ord("k") and self.recover_stage == "creating":
            self.mode, self.text = "typed", ""
        elif ch == ESC:
            self.done = True  # leave the record pending; Lookup and Create stay refused
        elif ord("1") <= ch <= ord("9") and ch - ord("1") < len(self.options):
            _, choice, _ = self.options[ch - ord("1")]
            self._try(lambda: self.p.answer(choice)) and self._finish()

    def _finish(self):
        self.done = True

    @staticmethod
    def _edit(text, ch):
        if ch in BACKSPACE:
            return text[:-1]
        if 32 <= ch < 127:
            return text + chr(ch)
        return text

    def _pump(self):
        if self.mode == "lookup":
            request = self.lookup.poll(datetime.now())
            if request is not None:
                self._search(*request)
        while True:
            try:
                seq, items, error = self.answers.get_nowait()
            except queue.Empty:
                return
            if error is not None:
                if seq == self.lookup.seq:
                    self.msg = f"search failed: {error}"
                    self.lookup.deliver(seq, [])
            else:
                self.lookup.deliver(seq, items)

    def _search(self, seq, jql):
        def work():
            try:
                self.answers.put((seq, self.p.search(jql), None))
            except Exception as e:
                self.answers.put((seq, [], e))

        threading.Thread(target=work, daemon=True).start()

    def _draw(self):
        scr = self.scr
        scr.erase()
        rows, _ = scr.getmaxyx()
        lines = self._lines()
        for i, line in enumerate(lines[: rows - 2]):
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
        if self.mode == "menu":
            return ["Ticket tab:  [l] Lookup   [c] Create   [s] Skip   [q] Quit"]
        if self.mode == "lookup":
            out = [f"Search: {self.lookup.text}", self.lookup.status(), ""]
            for i, issue in enumerate(self.lookup.results or []):
                mark = ">" if i == self.sel else " "
                out.append(f"{mark} {issue.key}  {issue.summary}")
            return out + ["", "Up/Down choose, Enter binds the tab, Esc back"]
        if self.mode == "create":
            return [f"Description: {self.text}", "", "Enter creates the ticket, Esc back"]
        if self.mode == "typed":
            return [f"Ticket key: {self.text}", "", "Enter confirms, Esc back"]
        if self.mode == "recover":
            if self.recover_stage == "creating":
                head = "Confirm this ticket for the pending tab?"
                if not self.options:
                    head = "The earlier create could not be confirmed."
                tail = "[k] type a key   [d] discard   [Esc] later"
            else:
                head = "Adopt a tab for the pending ticket, or open a new one."
                tail = "[n] new tab   [d] discard   [Esc] later"
            out = [head, ""]
            out += [f"{i + 1}. {label}" for i, (label, _, _) in enumerate(self.options[:9])]
            return out + ["", tail]
        return []
