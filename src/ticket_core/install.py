"""`herdr-ticket install` (D22): add the `$ticket` row to the agent layout. Never writes `[keys]`."""

import tomllib
from datetime import datetime
from pathlib import Path

ROW = "$ticket"
TITLE_ROW = "$ticket_title"
BLOCK = (
    "[ui.sidebar.agents]\n"
    'rows = [["state_icon", "machine", "workspace", "tab"], ["agent"], ["$ticket", "$ticket_title"]]\n'
)
KEYS_HINT = """\
Tab key (manual step M2; install does not write [keys]). Add to ~/.config/herdr/config.toml,
choosing a chord that is free in the default list:

[keys]
new_tab = "<free chord>"

[[keys.command]]
key = "prefix+c"
type = "plugin_action"
command = "herdr-ticket.new-ticket-tab"
description = "new ticket tab"
"""


class InstallError(Exception):
    pass


def _has_ticket_row(rows) -> bool:
    return any(isinstance(row, list) and ROW in row for row in rows or [])


def install(config_path, now: datetime, emit=print) -> tuple[bool, str]:
    """Returns (changed, message). Emits the planned change before any write."""
    path = Path(config_path)
    original = path.read_bytes() if path.exists() else None
    text = "" if original is None else original.decode()
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise InstallError(f"{path} is not valid TOML; not changed: {e}") from None

    agents = data.get("ui", {}).get("sidebar", {}).get("agents")
    if agents is not None:
        if _has_ticket_row(agents.get("rows")):
            return False, f"{ROW} is already a row in [ui.sidebar.agents]; nothing changed."
        return False, (
            f"[ui.sidebar.agents] already exists in {path}; nothing changed. "
            f'Add ["{ROW}", "{TITLE_ROW}"] as a row in rows by hand.'
        )

    head = text if not text or text.endswith("\n") else text + "\n"
    if head:
        head += "\n"
    new_text = head + BLOCK
    try:
        tomllib.loads(new_text)
    except tomllib.TOMLDecodeError as e:
        raise InstallError(f"the appended block is not valid TOML; {path} not changed: {e}") from None

    emit(f"Appending to {path}:\n{BLOCK}")
    backup = None
    if original is not None:
        backup = path.with_name(f"{path.name}.bak-{now:%Y%m%d%H%M%S}")
        with open(backup, "xb") as f:
            f.write(original)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new_text)

    message = f"Added [ui.sidebar.agents] with the {ROW} row to {path}."
    if backup is not None:
        message += f" Backup: {backup}."
    return True, message
