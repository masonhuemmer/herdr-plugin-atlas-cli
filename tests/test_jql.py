from datetime import datetime

from ticket_core.jql import build_jql, build_recovery_jql, normalise


def test_normalise_drops_wildcards_and_trims():
    assert normalise("  foo*? ") == "foo"
    assert normalise("*?  ") == ""


def test_key_branch_uppercases():
    assert build_jql("SDO-123") == 'key = "SDO-123"'
    assert build_jql("sdo-7") == 'key = "SDO-7"'


def test_text_branch_adds_trailing_wildcard():
    assert build_jql("fix login") == 'summary ~ "fix login*"'


def test_text_branch_escapes_quotes():
    assert build_jql('say "hi"') == 'summary ~ "say \\"hi\\"*"'


def test_text_branch_escapes_backslashes():
    assert build_jql("a\\b") == 'summary ~ "a\\\\b*"'


def test_empty_after_normalisation_gives_none():
    for text in ["", "   ", "*?", " * ? "]:
        assert build_jql(text) is None, repr(text)


def test_recovery_jql_window_and_escaping():
    jql = build_recovery_jql('say "hi"', datetime(2026, 10, 9, 14, 10))
    assert 'created >= "2026-10-09 14:05"' in jql
    assert 'summary ~ "say \\"hi\\""' in jql
    assert "currentUser()" in jql
    assert '*"' not in jql
