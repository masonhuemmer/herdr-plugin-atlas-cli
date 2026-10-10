"""Key handling for the picker screens, driven without a terminal. The drawing is manual (M4-M6)."""

import curses

from ticket_core.recovery import Issue, Prompt
from ticket_core.transactions import Refused
from ticket_core.ui import ESC, _Ui


class StubPicker:
    def __init__(self, stage=None, refuse=False):
        self.stage = stage
        self.refuse = refuse
        self.calls = []

    def pending_stage(self):
        return self.stage

    def skip(self):
        self.calls.append(("skip",))

    def bind(self, issue):
        self._record(("bind", issue.key))

    def create(self, text):
        self._record(("create", text))

    def answer(self, choice):
        self._record(("answer", choice))

    def search(self, jql):
        return []

    def _record(self, call):
        if self.refuse:
            raise Refused("a pending record exists")
        self.calls.append(call)


def _keys(ui, text):
    for ch in text:
        ui._key(ord(ch))


def _recovering(picker, prompt):
    ui = _Ui(scr=None, picker=picker)
    ui._recovery(prompt)
    return ui


def test_skip_from_the_menu_makes_the_tab_and_finishes():
    p = StubPicker()
    ui = _Ui(None, p)
    ui._key(ord("s"))
    assert p.calls == [("skip",)] and ui.done


def test_lookup_enter_binds_the_selected_result():
    p = StubPicker()
    ui = _Ui(None, p)
    ui._key(ord("l"))
    _keys(ui, "fix")
    ui.lookup.deliver(ui.lookup.seq, [Issue("EX-1", "a"), Issue("EX-2", "b")])
    ui._key(curses.KEY_DOWN)
    ui._key(10)
    assert p.calls == [("bind", "EX-2")] and ui.done


def test_a_refusal_is_shown_and_the_picker_stays_open():
    p = StubPicker(refuse=True)
    ui = _Ui(None, p)
    ui.mode = "create"
    _keys(ui, "Fix login")
    ui._key(10)
    assert ui.msg.startswith("refused:") and not ui.done


def test_create_sends_the_typed_description():
    p = StubPicker()
    ui = _Ui(None, p)
    ui._key(ord("c"))
    _keys(ui, "Fix login")
    ui._key(10)
    assert p.calls == [("create", "Fix login")] and ui.done


def test_recovery_digit_confirms_the_listed_key():
    p = StubPicker(stage="creating")
    ui = _recovering(p, Prompt([Issue("EX-9", "Fix login")], []))
    ui._key(ord("1"))
    assert p.calls == [("answer", ("confirm", "EX-9"))] and ui.done


def test_recovery_typed_key_is_uppercased_and_checked():
    p = StubPicker(stage="creating")
    ui = _recovering(p, Prompt([], []))
    ui._key(ord("k"))
    _keys(ui, "ex-9")
    ui._key(10)
    assert p.calls == [("answer", ("confirm", "EX-9"))]


def test_recovery_typed_key_must_look_like_a_key():
    p = StubPicker(stage="creating")
    ui = _recovering(p, Prompt([], []))
    ui._key(ord("k"))
    _keys(ui, "nope")
    ui._key(10)
    assert p.calls == [] and not ui.done and ui.msg


def test_recovery_offers_new_tab_only_for_tab_creating():
    p = StubPicker(stage="tab_creating")
    ui = _recovering(p, Prompt([], []))
    ui._key(ord("n"))
    assert p.calls == [("answer", ("new_tab",))] and ui.done


def test_recovery_escape_leaves_the_record_pending():
    p = StubPicker(stage="creating")
    ui = _recovering(p, Prompt([], []))
    ui._key(ESC)
    assert p.calls == [] and ui.done
