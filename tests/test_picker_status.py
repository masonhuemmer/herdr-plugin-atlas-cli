from test_picker import parts  # noqa: F401  (fixture)


def test_create_reports_the_jira_status_on_the_new_tab(parts):
    _, herdr, _, make = parts
    make().create("Login broken on Safari")
    assert "To Do" in herdr.statuses.values()


def test_lookup_bind_reports_the_jira_status_on_the_tab(parts):
    _, herdr, _, make = parts
    from ticket_core.recovery import Issue
    make().bind(Issue("SDO-9", "Fix login"))
    assert "To Do" in herdr.statuses.values()
