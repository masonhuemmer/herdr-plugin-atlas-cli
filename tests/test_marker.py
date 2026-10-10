from ticket_core.marker import Binding, format_marker, parse_marker


def test_parses_bound_label():
    assert parse_marker("ticket:v1 SDO-123 · Fix login") == Binding("SDO-123", "Fix login")


def test_rejects_malformed_labels():
    rejected = [
        "ticket:v1 sdo-123 · x",
        "ticket:v1 SDO-123 - x",
        "SDO-123 · x",
        "ticket:v1 SDO-123 · ",
        "ticket:v1 SDO-123 · a\nb",
        "SDO-123",
    ]
    for label in rejected:
        assert parse_marker(label) is None, label


def test_format_round_trips():
    label = format_marker("SDO-7", "Refactor auth")
    assert label == "ticket:v1 SDO-7 · Refactor auth"
    assert parse_marker(label) == Binding("SDO-7", "Refactor auth")
