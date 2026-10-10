import pytest

from ticket_core.config import ConfigError, load_config, session_name, ticket_home


def test_load_config_reads_all_four_keys(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('site = "acme"\nproject = "EX"\nissue_type = "Task"\nassignee = "acc-1"\n')
    cfg = load_config(path)
    assert (cfg.site, cfg.project, cfg.issue_type, cfg.assignee) == ("acme", "EX", "Task", "acc-1")


def test_load_config_names_every_missing_key(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('site = "acme"\n')
    with pytest.raises(ConfigError, match="project, issue_type, assignee"):
        load_config(path)


def test_missing_config_file_is_a_config_error(tmp_path):
    with pytest.raises(ConfigError):
        load_config(tmp_path / "absent.toml")


def test_session_name_comes_from_the_socket_path():
    assert session_name("~/.config/herdr/sessions/ticket-test/herdr.sock") == "ticket-test"
    assert session_name("/tmp/herdr.sock") == "default"
    assert session_name(None) == "default"


def test_ticket_home_follows_home(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert ticket_home() == tmp_path / ".config" / "herdr-plugin-atlas-cli"


def test_statuses_default_when_the_key_is_absent(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('site = "acme"\nproject = "EX"\nissue_type = "Task"\nassignee = "acc-1"\n')
    assert load_config(path).statuses == ("To Do", "In Progress", "Done")


def test_statuses_override_the_default(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('site = "acme"\nproject = "EX"\nissue_type = "Task"\nassignee = "acc-1"\n'
                    'statuses = ["Backlog", "Review"]\n')
    assert load_config(path).statuses == ("Backlog", "Review")


@pytest.mark.parametrize("value", ['"Done"', "[]", "[1]"])
def test_statuses_must_be_a_non_empty_list_of_names(tmp_path, value):
    path = tmp_path / "config.toml"
    path.write_text('site = "acme"\nproject = "EX"\nissue_type = "Task"\nassignee = "acc-1"\n'
                    f"statuses = {value}\n")
    with pytest.raises(ConfigError, match="statuses"):
        load_config(path)
