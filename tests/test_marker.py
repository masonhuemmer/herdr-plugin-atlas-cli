from ticket_core.marker import Binding, format_marker, parse_marker


def test_parses_bound_label():
    assert parse_marker("ticket:v1 EX-123 · Fix login") == Binding("EX-123", "Fix login")


def test_rejects_malformed_labels():
    rejected = [
        "ticket:v1 ex-123 · x",
        "ticket:v1 EX-123 - x",
        "EX-123 · x",
        "ticket:v1 EX-123 · ",
        "ticket:v1 EX-123 · a\nb",
        "EX-123",
    ]
    for label in rejected:
        assert parse_marker(label) is None, label


def test_format_round_trips():
    label = format_marker("EX-7", "Refactor auth")
    assert label == "ticket:v1 EX-7 · Refactor auth"
    assert parse_marker(label) == Binding("EX-7", "Refactor auth")
