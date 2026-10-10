from datetime import datetime, timedelta

from ticket_core.lookup import DEBOUNCE, LIMIT, Lookup

T0 = datetime(2026, 10, 10, 9, 0, 0)


def _at(seconds):
    return T0 + timedelta(seconds=seconds)


def test_text_input_waits_for_the_debounce():
    lk = Lookup()
    lk.type_text("fix", _at(0))
    assert lk.poll(_at(DEBOUNCE / 2)) is None
    assert lk.poll(_at(DEBOUNCE + 0.01)) == (1, 'summary ~ "fix*"')


def test_one_request_per_pause():
    lk = Lookup()
    lk.type_text("fix", _at(0))
    assert lk.poll(_at(1)) is not None
    assert lk.poll(_at(2)) is None


def test_stale_results_are_dropped_and_only_the_latest_text_shows():
    lk = Lookup()
    lk.type_text("a", _at(0))
    lk.type_text("ab", _at(0.1))
    assert lk.poll(_at(1)) == (2, 'summary ~ "ab*"')
    assert lk.deliver(1, [object()]) is False
    assert lk.results is None
    assert lk.deliver(2, ["item"]) is True
    assert lk.results == ["item"]


def test_empty_input_sends_no_request_and_drops_outstanding_results():
    lk = Lookup()
    lk.type_text("fix", _at(0))
    lk.poll(_at(1))
    lk.type_text("*? ", _at(1.1))
    assert lk.poll(_at(3)) is None
    assert lk.deliver(1, ["late"]) is False
    assert lk.results == []


def test_key_input_searches_by_key():
    lk = Lookup()
    lk.type_text("ex-12", _at(0))
    assert lk.poll(_at(1)) == (1, 'key = "EX-12"')


def test_a_full_page_says_keep_typing():
    lk = Lookup()
    lk.type_text("fix", _at(0))
    lk.poll(_at(1))
    lk.deliver(1, list(range(LIMIT)))
    assert lk.status() == "50+ matches — keep typing"


def test_a_short_page_has_no_status_line():
    lk = Lookup()
    lk.type_text("fix", _at(0))
    lk.poll(_at(1))
    lk.deliver(1, [1, 2, 3])
    assert lk.status() == ""
