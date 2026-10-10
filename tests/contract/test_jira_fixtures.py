import pytest

from fake_run import FakeRun, fixture_text
from ticket_core.adapters.jira import AtlasError, AtlasJira
from ticket_core.recovery import Issue

ATLAS = "/opt/homebrew/bin/atlas"
SITE = "sesamidevel"


def _jira(run):
    return AtlasJira(run=run, atlas=ATLAS)


def test_search_fixture_parses_to_issues():
    run = FakeRun(stdout=fixture_text("jira_search_reporter.json"))
    issues = _jira(run).search("reporter = currentUser()", SITE)
    assert len(issues) == 6
    assert issues[0] == Issue("SDO-601", issues[0].summary)
    assert issues[0].summary.startswith("Let's Encrypt with cert-manager")
    assert issues[1].key == "SDO-600"


def test_search_argv_is_exact_and_passes_site():
    run = FakeRun(stdout=fixture_text("jira_search_reporter.json"))
    _jira(run).search("reporter = currentUser()", SITE)
    assert run.argv == [[ATLAS, "jira", "search", "--jql", "reporter = currentUser()",
                         "--site", SITE]]


def test_search_nonzero_exit_raises_atlas_error_with_stderr():
    run = FakeRun(stderr="usage: bad flag", returncode=3)
    with pytest.raises(AtlasError, match="usage: bad flag"):
        _jira(run).search("project = SDO", SITE)


def test_create_argv_has_site_and_no_description():
    run = FakeRun(stdout='{"key": "SDO-1"}')
    key = _jira(run).create("SDO", "Task", "Fix login", "acc-1", SITE)
    assert key == "SDO-1"
    argv = run.argv[0]
    assert argv == [ATLAS, "jira", "create", "--project", "SDO", "--type", "Task",
                    "--summary", "Fix login", "--assignee", "acc-1", "--site", SITE]
    assert "--description" not in argv
    assert "--dry-run" not in argv


def test_create_dry_run_fixture_has_no_key_and_returns_none():
    run = FakeRun(stdout=fixture_text("jira_dry_run_create.json"))
    key = _jira(run).create("SDO", "Task", "herdr-ticket dry run", "acc-1", SITE, dry_run=True)
    assert key is None
    assert run.argv[0][-1] == "--dry-run"


def test_create_without_key_in_real_output_raises():
    run = FakeRun(stdout='{"unexpected": true}')
    with pytest.raises(AtlasError, match="no key"):
        _jira(run).create("SDO", "Task", "Fix login", "acc-1", SITE)


def test_comment_dry_run_fixture_and_flag_only_when_requested():
    run = FakeRun(stdout=fixture_text("jira_dry_run_comment.json"))
    _jira(run).comment("SDO-601", "herdr-ticket dry run", SITE, dry_run=True)
    _jira(run).comment("SDO-601", "herdr-ticket dry run", SITE)
    dry, real = run.argv
    assert dry[-1] == "--dry-run"
    assert dry[:6] == [ATLAS, "jira", "comment", "SDO-601", "--body", "herdr-ticket dry run"]
    assert "--site" in dry and dry[dry.index("--site") + 1] == SITE
    assert "--dry-run" not in real
