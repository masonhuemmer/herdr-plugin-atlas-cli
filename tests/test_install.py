import tomllib
from datetime import datetime

import pytest

import ticket_core.install as install_mod
from ticket_core.install import InstallError, install

NOW = datetime(2026, 10, 10, 12, 0, 0)
ROW = ["$ticket", "$ticket_title"]


def _rows(path):
    return tomllib.loads(path.read_text())["ui"]["sidebar"]["agents"]["rows"]


def test_missing_config_is_created_with_the_block_and_no_backup(tmp_path):
    path = tmp_path / "herdr" / "config.toml"
    changed, _ = install(path, NOW, emit=lambda s: None)
    assert changed is True
    assert ROW in _rows(path)
    assert list(tmp_path.rglob("*.bak-*")) == []


def test_existing_config_gets_a_backup_and_keeps_its_text(tmp_path):
    path = tmp_path / "config.toml"
    original = '[ui]\nsidebar_collapsed_mode = "auto"\n\n[ui.toast]\nenabled = true\n'
    path.write_text(original)

    changed, _ = install(path, NOW, emit=lambda s: None)

    assert changed is True
    backup = tmp_path / "config.toml.bak-20261010120000"
    assert backup.read_text() == original
    new = path.read_text()
    assert new.startswith(original)
    assert ROW in _rows(path)
    assert tomllib.loads(new)["ui"]["toast"] == {"enabled": True}


def test_existing_agents_table_is_left_alone_and_the_row_is_named(tmp_path):
    path = tmp_path / "config.toml"
    original = '[ui.sidebar.agents]\nrows = [["agent"]]\n'
    path.write_text(original)

    changed, message = install(path, NOW, emit=lambda s: None)

    assert changed is False
    assert path.read_text() == original
    assert list(tmp_path.glob("*.bak-*")) == []
    assert '["$ticket", "$ticket_title"]' in message


def test_a_row_that_already_names_ticket_changes_nothing(tmp_path):
    path = tmp_path / "config.toml"
    original = '[ui.sidebar.agents]\nrows = [["agent"], ["$ticket"]]\n'
    path.write_text(original)
    changed, message = install(path, NOW, emit=lambda s: None)
    assert changed is False and path.read_text() == original
    assert "already" in message


def test_second_run_changes_nothing_and_writes_no_second_backup(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("[ui]\nx = 1\n")
    install(path, NOW, emit=lambda s: None)
    after_first = path.read_text()

    changed, _ = install(path, datetime(2026, 10, 10, 13, 0, 0), emit=lambda s: None)

    assert changed is False
    assert path.read_text() == after_first
    assert len(list(tmp_path.glob("config.toml.bak-*"))) == 1


def test_invalid_toml_from_the_append_is_never_written(tmp_path, monkeypatch):
    path = tmp_path / "config.toml"
    original = "[ui]\nx = 1\n"
    path.write_text(original)
    monkeypatch.setattr(install_mod, "BLOCK", "[ui.sidebar.agents\nrows = [")

    with pytest.raises(InstallError):
        install(path, NOW, emit=lambda s: None)

    assert path.read_text() == original
    assert list(tmp_path.glob("*.bak-*")) == []


def test_invalid_existing_config_is_refused_before_any_write(tmp_path):
    path = tmp_path / "config.toml"
    original = "[ui\nx = \n"
    path.write_text(original)
    with pytest.raises(InstallError):
        install(path, NOW, emit=lambda s: None)
    assert path.read_text() == original
    assert list(tmp_path.glob("*.bak-*")) == []


def test_the_planned_change_is_emitted_before_the_write(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("[ui]\nx = 1\n")
    seen = []
    install(path, NOW, emit=lambda s: seen.append((s, path.read_text())))
    [(message, text_at_emit)] = seen
    assert "$ticket" in message
    assert text_at_emit == "[ui]\nx = 1\n"
