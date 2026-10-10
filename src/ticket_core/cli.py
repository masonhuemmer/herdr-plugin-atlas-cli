"""Plugin entry point. bin/herdr-ticket runs `python3 -m ticket_core.cli <command>`."""

import argparse
import os
import subprocess
import sys
from datetime import datetime

from ticket_core.adapters.herdr import DEFAULT_HERDR, HerdrAdapter, HerdrError
from ticket_core.adapters.jira import AtlasError, AtlasJira
from ticket_core.config import ConfigError, herdr_config_path, load_config, session_dir, ticket_home
from ticket_core.install import KEYS_HINT, InstallError, install
from ticket_core.picker import Picker, crash_checkpoint, read_capture, write_capture
from ticket_core.state import Busy, StateStore
from ticket_core.sync import snapshot_with_retry, sync_tokens
from ticket_core.transactions import Refused, apply_site_change

PLUGIN_ID = "herdr-ticket"


class CliError(Exception):
    pass


def _config():
    return load_config(ticket_home() / "config.toml")


def _need(env, name: str) -> str:
    try:
        return env[name]
    except KeyError:
        raise CliError(f"{name} is not set; run this from a Herdr plugin action") from None


def cmd_startup(env, herdr=None) -> None:
    config = _config()
    herdr = herdr or HerdrAdapter()
    store = StateStore(session_dir(env) / "state.json")
    snapshot_with_retry(herdr)  # restored tabs must be in the snapshot before the site check
    try:
        apply_site_change(store, herdr, config.site)
    except Busy:
        print("herdr-ticket: picker holds the state lock; site check skipped", file=sys.stderr)
    sync_tokens(herdr)


def cmd_reconcile(env, herdr=None) -> None:
    sync_tokens(herdr or HerdrAdapter())


def cmd_open_picker(env, run=subprocess.run) -> None:
    write_capture(session_dir(env), _need(env, "HERDR_ACTIVE_WORKSPACE_ID"),
                  _need(env, "HERDR_ACTIVE_PANE_CWD"))
    herdr = env.get("HERDR_BIN_PATH") or DEFAULT_HERDR
    run([herdr, "plugin", "pane", "open", "--plugin", PLUGIN_ID, "--entrypoint", "picker"],
        check=True)


def cmd_picker(env, herdr=None, jira=None) -> int:
    from ticket_core.ui import run  # imports curses; kept off the other commands

    config = _config()
    directory = session_dir(env)
    try:
        capture = read_capture(directory)
    except FileNotFoundError:
        raise CliError("no capture from the plugin action; open the picker with prefix+c") from None
    picker = Picker(
        store=StateStore(directory / "state.json"), herdr=herdr or HerdrAdapter(),
        jira=jira or AtlasJira(), site=config.site, project=config.project,
        issue_type=config.issue_type, assignee=config.assignee, capture=capture,
        now=datetime.now, checkpoint=crash_checkpoint(env),
    )
    return run(picker)


def cmd_install(env, emit=print) -> None:
    _config()  # the plugin config must be complete before anything is written
    _, message = install(herdr_config_path(), datetime.now(), emit=emit)
    emit(message)
    emit(KEYS_HINT)


def main(argv=None, env=None) -> int:
    parser = argparse.ArgumentParser(prog="herdr-ticket")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("startup", "reconcile", "open-picker", "picker", "install"):
        sub.add_parser(name)
    args = parser.parse_args(argv)
    env = dict(os.environ) if env is None else env
    try:
        if args.command == "startup":
            cmd_startup(env)
        elif args.command == "reconcile":
            cmd_reconcile(env)
        elif args.command == "open-picker":
            cmd_open_picker(env)
        elif args.command == "picker":
            return cmd_picker(env)
        elif args.command == "install":
            cmd_install(env)
    except (CliError, ConfigError, InstallError, HerdrError, AtlasError, Busy, Refused) as e:
        print(f"herdr-ticket: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
