"""Plugin entry point. bin/herdr-ticket runs `python3 -m ticket_core.cli <command>`."""

import argparse
import json
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
from ticket_core.status_menu import (
    apply_status, bound_binding, read_status_capture, write_status_capture,
)
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


def _status_sync_args(env, config_site) -> dict:
    return {"jira": AtlasJira(), "site": config_site,
            "cache_path": session_dir(env) / "statuses.json"}


def cmd_startup(env, herdr=None) -> None:
    config = _config()
    herdr = herdr or HerdrAdapter()
    store = StateStore(session_dir(env) / "state.json")
    snapshot_with_retry(herdr)  # restored tabs must be in the snapshot before the site check
    try:
        apply_site_change(store, herdr, config.site)
    except Busy:
        print("herdr-ticket: picker holds the state lock; site check skipped", file=sys.stderr)
    sync_tokens(herdr, **_status_sync_args(env, config.site))


def cmd_reconcile(env, herdr=None) -> None:
    # Runs on every pane creation in every session; without a config it still clears tokens.
    try:
        site = _config().site
    except ConfigError:
        site = None
    args = _status_sync_args(env, site) if site else {}
    sync_tokens(herdr or HerdrAdapter(), **args)


def _plugin_context(env) -> dict:
    raw = env.get("HERDR_PLUGIN_CONTEXT_JSON")
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except ValueError:
        return {}


def _action_workspace_and_cwd(env) -> tuple[str, str]:
    # Plugin actions get HERDR_WORKSPACE_ID and HERDR_PLUGIN_CONTEXT_JSON (plugins.mdx, v0.9.1);
    # HERDR_ACTIVE_* is what custom keybinding commands get, kept as a fallback.
    context = _plugin_context(env)
    workspace = env.get("HERDR_WORKSPACE_ID") or env.get("HERDR_ACTIVE_WORKSPACE_ID") \
        or context.get("workspace_id")
    cwd = context.get("focused_pane_cwd") or context.get("workspace_cwd") \
        or env.get("HERDR_ACTIVE_PANE_CWD")
    if not workspace or not cwd:
        raise CliError("no workspace or cwd in the plugin action environment; run this from a Herdr plugin action")
    return workspace, cwd


def cmd_open_picker(env, run=subprocess.run) -> None:
    workspace, cwd = _action_workspace_and_cwd(env)
    write_capture(session_dir(env), workspace, cwd)
    herdr = env.get("HERDR_BIN_PATH") or DEFAULT_HERDR
    run([herdr, "plugin", "pane", "open", "--plugin", PLUGIN_ID, "--entrypoint", "picker"],
        check=True)


def cmd_open_status(env, run=subprocess.run) -> None:
    context = _plugin_context(env)
    pane_id = context.get("focused_pane_id")
    if not pane_id:
        raise CliError("no focused pane in the plugin action environment; run this from a Herdr plugin action")
    write_status_capture(session_dir(env), pane_id)
    herdr = env.get("HERDR_BIN_PATH") or DEFAULT_HERDR
    run([herdr, "plugin", "pane", "open", "--plugin", PLUGIN_ID, "--entrypoint", "status"],
        check=True)


def cmd_status(env, herdr=None, jira=None, run_ui=None) -> int:
    from ticket_core.status_ui import run  # imports curses; kept off the other commands

    directory = session_dir(env)
    try:
        pane_id = read_status_capture(directory)
    except FileNotFoundError:
        raise CliError("no capture from the plugin action; open the status menu from a bound tab") from None
    herdr = herdr or HerdrAdapter()
    binding = bound_binding(herdr.snapshot(), pane_id)
    show = run_ui or run
    if binding is None:
        return show(None, [], None)  # no Jira call for an unbound tab
    config = _config()
    jira = jira or AtlasJira()

    def choose(status: str) -> None:
        apply_status(binding.key, status, jira=jira, herdr=herdr, site=config.site,
                     cache_path=directory / "statuses.json")

    return show(binding.key, list(config.statuses), choose)


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
        cache_path=directory / "statuses.json",
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
    for name in ("startup", "reconcile", "open-picker", "picker", "install", "open-status", "status"):
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
        elif args.command == "open-status":
            cmd_open_status(env)
        elif args.command == "status":
            return cmd_status(env)
    except (CliError, ConfigError, InstallError, HerdrError, AtlasError, Busy, Refused) as e:
        print(f"herdr-ticket: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
