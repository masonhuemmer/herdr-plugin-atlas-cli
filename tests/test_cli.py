import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

from fakes import FakeHerdr, FakeJira
from ticket_core import cli
from ticket_core.config import herdr_config_path, ticket_home
from ticket_core.picker import read_capture
from ticket_core.state import State, StateStore

ROOT = Path(__file__).resolve().parent.parent
CONFIG = 'site = "acme"\nproject = "SDO"\nissue_type = "Task"\nassignee = "acc-1"\n'


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


def _write_config(home):
    d = home / ".config" / "herdr-ticket"
    d.mkdir(parents=True, exist_ok=True)
    (d / "config.toml").write_text(CONFIG)


def _env(home, socket="/x/sessions/ticket-test/herdr.sock"):
    return {"HOME": str(home), "HERDR_SOCKET_PATH": socket}


def test_open_picker_writes_the_capture_and_opens_the_overlay(home):
    env = {**_env(home), "HERDR_ACTIVE_WORKSPACE_ID": "w7", "HERDR_ACTIVE_PANE_CWD": "/work",
           "HERDR_BIN_PATH": "/bin/herdr-x"}
    calls = []
    cli.cmd_open_picker(env, run=lambda argv, **kw: calls.append((argv, kw)))

    session = ticket_home() / "ticket-test"
    assert read_capture(session).workspace_id == "w7"
    assert read_capture(session).cwd == "/work"
    [(argv, kw)] = calls
    assert argv == ["/bin/herdr-x", "plugin", "pane", "open", "--plugin", "herdr-ticket",
                    "--entrypoint", "picker"]
    assert kw == {"check": True}


def test_open_picker_without_the_plugin_env_is_a_clear_error(home):
    assert cli.main(["open-picker"], env=_env(home)) == 1


def test_startup_records_the_site_and_syncs_tokens(home):
    _write_config(home)
    herdr = FakeHerdr()
    tab, root = herdr.add_tab("ticket:v1 SDO-5 · Fix login", "w1")
    cli.cmd_startup(_env(home), herdr=herdr)
    assert herdr.tokens == {root: "SDO-5"}
    assert StateStore(ticket_home() / "ticket-test" / "state.json").read().site == "acme"


def test_startup_with_a_changed_site_unbinds_then_syncs(home):
    _write_config(home)
    state_dir = ticket_home() / "ticket-test"
    state_dir.mkdir(parents=True)
    store = StateStore(state_dir / "state.json")
    store.write(State(site="old", pending=None))
    herdr = FakeHerdr()
    tab, root = herdr.add_tab("ticket:v1 SDO-5 · Fix login", "w1")
    cli.cmd_startup(_env(home), herdr=herdr)
    assert herdr.tabs[tab]["label"] == "Fix login"
    assert herdr.tokens == {}
    assert store.read().site == "acme"


def test_startup_without_config_fails_before_touching_state(home):
    assert cli.main(["startup"], env=_env(home)) == 1
    assert not (ticket_home() / "ticket-test").exists()


def test_reconcile_needs_no_config(home):
    herdr = FakeHerdr()
    tab, root = herdr.add_tab("ticket:v1 SDO-5 · Fix login", "w1")
    cli.cmd_reconcile(_env(home), herdr=herdr)
    assert herdr.tokens == {root: "SDO-5"}


def test_install_refuses_without_plugin_config_and_writes_nothing(home):
    assert cli.main(["install"], env=_env(home)) == 1
    assert not herdr_config_path().exists()


def test_install_writes_the_row_and_prints_the_keys_hint(home, capsys):
    _write_config(home)
    assert cli.main(["install"], env=_env(home)) == 0
    assert '["$ticket"]' in herdr_config_path().read_text()
    out = capsys.readouterr().out
    assert 'command = "herdr-ticket.new-ticket-tab"' in out
    assert "[[keys.command]]" in out


def test_install_is_safe_to_run_twice(home):
    _write_config(home)
    cli.main(["install"], env=_env(home))
    before = herdr_config_path().read_text()
    assert cli.main(["install"], env=_env(home)) == 0
    assert herdr_config_path().read_text() == before
    assert len(list(herdr_config_path().parent.glob("config.toml.bak-*"))) == 0  # first run was a create


def test_wrapper_runs_install_end_to_end_under_a_temp_home(home):
    _write_config(home)
    env = {"HOME": str(home), "PATH": os.environ["PATH"]}  # the PATH the shell gives python3
    proc = subprocess.run(["sh", "bin/herdr-ticket", "install"], cwd=ROOT, env=env,
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert '["$ticket"]' in herdr_config_path().read_text()
