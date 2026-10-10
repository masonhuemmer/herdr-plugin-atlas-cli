# Herdr Atlas CLI

A [Herdr](https://herdr.dev) plugin that binds a terminal tab to a Jira ticket.
The ticket key and its status show in the Herdr sidebar, next to the agent
running in that tab.

- **New ticket tab** (`prefix+t`): look up an existing ticket, create a new one
  from a description, or skip and open a plain tab.
- **Sidebar**: each bound agent shows `KEY · Status`, for example `PROJ-12 · In Progress`.
- **Set status** (`prefix+m`): move the bound ticket to To Do, In Progress, or Done.
- **Refresh** (`prefix+u`): reload tickets now instead of waiting for the cache.

Jira is reached through atlas, the Atlassian CLI, so atlas must be installed and
signed in before the plugin can reach Jira.

## Requirements

- Herdr 0.9.1 or later on macOS or Linux
- Python 3.11 or later (stdlib only at runtime)
- atlas, signed in to your Jira site

## Install

```sh
herdr plugin link /path/to/herdr-plugin-atlas-cli
sh /path/to/herdr-plugin-atlas-cli/bin/herdr-plugin-atlas-cli install
```

`install` adds the sidebar row to `~/.config/herdr/config.toml`, backing up the
file first. It prints the keybinding snippet; add it to `[keys]` yourself.

## Configure

Create `~/.config/herdr-plugin-atlas-cli/config.toml`:

```toml
site = "your-site"           # the atlas site alias
project = "PROJ"             # project key for new tickets
issue_type = "Task"
assignee = "your-account-id" # Jira account ID
# statuses = ["To Do", "In Progress", "Done"]   # optional
```

## Test

```sh
python3 -m venv .venv && .venv/bin/pip install pytest
TMPDIR=/tmp .venv/bin/python -m pytest -q
```

The tests use recorded fixtures and fakes; they never call Jira or Herdr.

## Status

Early. Expect changes to keybindings and the sidebar layout.
