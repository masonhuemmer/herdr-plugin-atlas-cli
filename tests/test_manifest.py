import os
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _manifest():
    return tomllib.loads((ROOT / "herdr-plugin.toml").read_text())


def test_manifest_declares_the_plugin_surface():
    m = _manifest()
    assert m["id"] == "herdr-plugin-atlas-cli"
    assert [a["id"] for a in m["actions"]] == ["new-ticket-tab", "set-status", "reconcile"]
    assert m["panes"][0]["id"] == "picker" and m["panes"][0]["placement"] == "overlay"
    assert [e["on"] for e in m["events"]] == ["pane.created", "tab.renamed"]
    assert m["startup"][0]["command"] == ["sh", "bin/herdr-plugin-atlas-cli", "startup"]


def test_every_command_runs_the_wrapper_from_the_plugin_root():
    m = _manifest()
    commands = [x["command"] for x in m["actions"] + m["panes"] + m["events"] + m["startup"]]
    for argv in commands:
        assert argv[:2] == ["sh", "bin/herdr-plugin-atlas-cli"], argv
    assert os.access(ROOT / "bin" / "herdr-plugin-atlas-cli", os.X_OK)


def test_manifest_declares_the_status_action_and_pane():
    m = _manifest()
    actions = {a["id"]: a for a in m["actions"]}
    panes = {p["id"]: p for p in m["panes"]}
    assert actions["set-status"]["command"] == ["sh", "bin/herdr-plugin-atlas-cli", "open-status"]
    assert panes["status"]["placement"] == "overlay"
    assert panes["status"]["command"] == ["sh", "bin/herdr-plugin-atlas-cli", "status"]
