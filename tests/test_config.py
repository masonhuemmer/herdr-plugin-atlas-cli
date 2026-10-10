import pytest

from ticket_core.config import ConfigError, load_config, session_name, ticket_home


def test_load_config_reads_all_four_keys(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('site = "acme"\nproject = "SDO"\nissue_type = "Task"\nassignee = "acc-1"\n')
    cfg = load_config(path)
    assert (cfg.site, cfg.project, cfg.issue_type, cfg.assignee) == ("acme", "SDO", "Task", "acc-1")


def test_load_config_names_every_missing_key(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('site = "acme"\n')
    with pytest.raises(ConfigError, match="project, issue_type, assignee"):
        load_config(path)


def test_missing_config_file_is_a_config_error(tmp_path):
    with pytest.raises(ConfigError):
        load_config(tmp_path / "absent.toml")


def test_session_name_comes_from_the_socket_path():
    assert session_name("/Users/mason/.config/herdr/sessions/ticket-test/herdr.sock") == "ticket-test"
    assert session_name("/tmp/herdr.sock") == "default"
    assert session_name(None) == "default"


def test_ticket_home_follows_home(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert ticket_home() == tmp_path / ".config" / "herdr-ticket"
