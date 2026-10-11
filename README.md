# Herdr Atlas CLI plugin

Show the Jira ticket assigned to each Herdr agent pane, including its **exact column on a selected Jira Software board**. The plugin is written in Go and uses the `atlas` CLI for Jira authentication and API calls. Herdr supplies pane and agent state. Kanban and Scrum boards use the same column lookup.

The plugin keeps Herdr's agent state separate from Jira status. It reports the ticket key, summary, and a colored column label to the Agent sidebar. A focused pane can open ticket details, use a currently available Jira transition, or request an on-demand Haiku progress draft. Drafts require review before any Jira comment is posted. No model runs in the background.

## Requirements

- Herdr 0.9.1 or later.
- An Atlas build with `jira boards`, `jira board placement`, `jira transitions`, `jira suggest`, and paginated `jira search` commands, signed in to the Jira site.
- Go 1.25 or later when building from source. The manifest builds one native executable at install time.
- Claude Code CLI only for the optional draft action.

The manifest supports macOS, Linux, and Windows. The same binary filename ends in `.exe` on all platforms so the manifest has one command path; Unix systems execute it normally.

## Build and configure

```sh
go build -o herdr-plugin-atlas-cli.exe ./cmd/herdr-plugin-atlas-cli
herdr plugin link .
herdr plugin config-dir herdr-plugin-atlas-cli
```

Create `config.toml` in the directory printed by `herdr plugin config-dir`:

```toml
site = "sesamidevel"
project = "SDO"        # needed for creating tickets
issue_type = "Task"    # needed for creating tickets
assignee = "ACCOUNT_ID" # optional; Atlas's default applies when omitted

[boards]
SDO = 1234            # choose the actual Jira Software board ID

[colors]
"1234/In Progress" = "🟡" # optional display override
```

Use `atlas jira boards --project SDO --site sesamidevel` to find the board ID. With no configured board, the picker discovers boards and asks when there is more than one. `atlas` and `herdr` are resolved from `PATH`; set `atlas` in `config.toml` or `ATLAS_BIN_PATH` when needed. The plugin keeps no Jira credential.

Run `./herdr-plugin-atlas-cli.exe install` to preview the Agent sidebar row and suggested keybindings. It appends a sidebar block only when none exists, backs up the original file, and never overwrites existing rows or keys. Add the suggested `[[keys.command]]` entries to your Herdr config using chords that are free in your keymap.

The manifest action IDs retain the existing plugin ID and bindings: `new-ticket-tab`, `set-status`, and `reconcile`. It adds `ticket-detail` and `draft-update`. The `reconcile` action forces a Jira refresh; startup and pane events use the five-minute placement cache.

## Using it

- **Attach:** open the picker to see up to ten of your recently updated active tickets, falling back to active project tickets if none are assigned to you. Type to filter them immediately; after a 300 ms pause, Jira issue-picker suggestions widen the candidate list. A typo of one character in a summary word can still match a recent ticket. Use ↑/↓ and Enter to select, or Esc to close. Enter an exact issue key to fetch it directly; prefix a summary with `+` to create a task. The list loads up to 50 recent candidates, while Jira suggestions search beyond that page. Non-interactive input retains the line prompt. A pending create is saved before the Jira call; after an uncertain result, the picker asks you to find or discard that issue rather than create another one.
- **Ticket environment:** choosing a new ticket tab starts its shell with `FACTORY_TICKET=KEY`, whether the ticket was created or selected. Agents started in that tab inherit it. Binding a ticket to an existing pane updates Herdr's ticket metadata; the environment of a running agent cannot be changed after launch.
- **Column:** the sidebar shows the selected board's exact column name. `Not on board`, `Unmapped status`, `Board unavailable`, and `Stale` are shown explicitly. A changed agent session in the same pane shows `Verify ticket` until confirmed in detail.
- **Detail:** shows the board, status, assignee, refresh time, and validated Jira link. Open uses the server machine's default browser. Set `remote = true` in plugin config when the Herdr server is remote; detail offers the link for copying instead.
- **Transition:** lists transitions Jira currently allows and previews the destination board column when mapped.
- **Draft:** reads at most 120 recent unwrapped terminal rows for an idle agent (the visible screen while working), normalizes output, and limits evidence to 8 KiB. Unchanged evidence makes no Haiku call. A draft may be edited, copied, or posted as an explicitly selected public comment or internal JSM note.

Existing `ticket:v1` pane labels remain visible with `Select board`. Open ticket detail to choose a board and convert that pane to `ticket:v2`. Labels and state are scoped to one Herdr session; changing the configured Jira site clears old bindings, as the Python plugin did.

## Development

```sh
go test ./...
go vet ./...
GOOS=windows GOARCH=amd64 go build -o /tmp/herdr-plugin-atlas-cli-windows.exe ./cmd/herdr-plugin-atlas-cli
```

The plugin's Go tests exercise per-pane placement, session verification, legacy markers, URL validation, draft deduplication, and uncertain create recovery. The Atlas repository tests its REST and JSON board contract separately.
