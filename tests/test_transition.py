from test_picker import parts  # noqa: F401  (fixture)


def test_create_moves_the_new_ticket_to_in_progress(parts):
    _, herdr, jira, make = parts
    make().create("Login broken on Safari")
    assert jira.transitions == [("SDO-9", "In Progress")]


def test_failed_transition_keeps_the_created_ticket_bound(parts):
    _, herdr, jira, make = parts
    jira.fail_transition = True
    make().create("Login broken on Safari")
    assert jira.creates and herdr.tabs  # the ticket exists and the tab is still bound
    assert "SDO-9" in {t["label"] for t in herdr.tabs.values()} or "SDO-9" in herdr.tokens.values()
