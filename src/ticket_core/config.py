"""Plugin config (`~/.config/herdr-plugin-atlas-cli/config.toml`) and per-session paths. Stdlib only."""

import tomllib
from dataclasses import dataclass
from pathlib import Path

REQUIRED = ("site", "project", "issue_type", "assignee")
DEFAULT_STATUSES = ("To Do", "In Progress", "Done")


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Config:
    site: str
    project: str
    issue_type: str
    assignee: str
    statuses: tuple[str, ...] = DEFAULT_STATUSES


def ticket_home() -> Path:
    return Path("~/.config/herdr-plugin-atlas-cli").expanduser()


def herdr_config_path() -> Path:
    return Path("~/.config/herdr/config.toml").expanduser()


def load_config(path: Path) -> Config:
    try:
        raw = tomllib.loads(Path(path).read_text())
    except FileNotFoundError:
        raise ConfigError(f"no config at {path}") from None
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"invalid config at {path}: {e}") from None
    missing = [k for k in REQUIRED if not raw.get(k)]
    if missing:
        raise ConfigError(f"config at {path} is missing: {', '.join(missing)}")
    return Config(**{k: str(raw[k]) for k in REQUIRED}, statuses=_statuses(raw, path))


def _statuses(raw, path) -> tuple[str, ...]:
    if "statuses" not in raw:
        return DEFAULT_STATUSES
    value = raw["statuses"]
    if not isinstance(value, list) or not value or not all(isinstance(v, str) and v for v in value):
        raise ConfigError(f"statuses in {path} must be a non-empty list of status names")
    return tuple(value)


def session_name(socket_path: str | None) -> str:
    """The segment after `sessions/` in the socket path (D3), or `default`."""
    if socket_path:
        parts = socket_path.split("/")
        if "sessions" in parts:
            i = parts.index("sessions")
            if i + 1 < len(parts) and parts[i + 1]:
                return parts[i + 1]
    return "default"


def session_dir(env) -> Path:
    return ticket_home() / session_name(env.get("HERDR_SOCKET_PATH"))
