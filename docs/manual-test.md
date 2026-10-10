# Manual test script: herdr-ticket Phase 4

**Status: not yet run.** Written by the Phase 4 code pass. Every step below is for the operator.

Run only in the named session `ticket-test` (`--session ticket-test`), and only against the Jira sandbox project. Do not run any step against the normal Herdr session. The gate is in `plan.md`, Phase 4, Manual.

## Before you start

- Phase 3 gate is met: `docs/sandbox-create.md` records a real sandbox create.
- `python3 --version` is 3.11 or later. The wrapper runs `python3` from the PATH Herdr gives the plugin. `/usr/bin/python3` is 3.9 on this machine and will fail to import.
- Automated checks are green: `cd ~/src/herdr-ticket && TMPDIR=<scratchpad> .venv/bin/python -m pytest -q`.
- Herdr is `/Users/mason/.local/bin/herdr` (0.9.1). Set `HERDR_BIN_PATH` if it differs.
- Values you need: `<SITE>` (the Jira site alias), `<SANDBOX_PROJECT>`, `<OPERATOR_ACCOUNT_ID>`, `<FREE_CHORD>` (a chord unused in the default key list), `<KEY>` (a sandbox ticket key).

## Checklist

- [x] **M1 Config.** (run 2026-10-10: config written, install appended `[ui.sidebar.agents]` with backup `config.toml.bak-20261010131511`, second run reported nothing changed. Reload step not yet run.) Create `~/.config/herdr-ticket/config.toml` with `site = "<SITE>"`, `project = "<SANDBOX_PROJECT>"`, `issue_type = "Task"`, `assignee = "<OPERATOR_ACCOUNT_ID>"`. Run `sh ~/src/herdr-ticket/bin/herdr-ticket install`.
  - Expected: the planned change is printed, then `Added [ui.sidebar.agents] ...` with a backup path, then the `[keys]` snippet. A `config.toml.bak-<YYYYmmddHHMMSS>` file exists next to `~/.config/herdr/config.toml`. The file has `["$ticket"]` in `rows`.
  - Run `sh ~/src/herdr-ticket/bin/herdr-ticket install` a second time. Expected: `nothing changed`, and no second backup.
  - Run `/Users/mason/.local/bin/herdr server reload-config`.

- [ ] **M2 Key.** Add the snippet below to `~/.config/herdr/config.toml`, with `new_tab` moved to a free chord (install does not write `[keys]`). Run `/Users/mason/.local/bin/herdr server reload-config`.
  ```toml
  [keys]
  new_tab = "<FREE_CHORD>"

  [[keys.command]]
  key = "prefix+c"
  type = "plugin_action"
  command = "herdr-ticket.new-ticket-tab"
  description = "new ticket tab"
  ```
  - Expected: `prefix+c` opens the picker overlay, and the built-in tab-name prompt no longer appears. `<FREE_CHORD>` opens a plain tab.
  - Record: the `[[keys.command]]` schema the server accepted, including whether `plugin_action` is valid in 0.9.1 (the local `--default-config` comments list only `shell`, `pane` and `popup`).

- [ ] **M3 Plugin.** In the `ticket-test` session, run `/Users/mason/.local/bin/herdr plugin link ~/src/herdr-ticket`, then `/Users/mason/.local/bin/herdr plugin action list --plugin herdr-ticket`.
  - Expected: `new-ticket-tab` and `reconcile` are listed. The link succeeds with the `pane.created` and `tab.renamed` events.
  - If the link refuses either event name, stop and re-open the design (plan D5, design "Display contract").
  - Expected: per-session state appears under `~/.config/herdr-ticket/ticket-test/` after the first run (D3).

- [ ] **M4 Lookup and env.** Press `prefix+c`. Type `sdo-` and then `<KEY>`, then choose the result.
  - Expected: a new focused tab labelled `ticket:v1 <KEY> · <summary>` (check with `/Users/mason/.local/bin/herdr tab list`).
  - Record in this file: the picker's captured env names (`HERDR_ACTIVE_WORKSPACE_ID`, `HERDR_ACTIVE_PANE_CWD`) as present in `~/.config/herdr-ticket/ticket-test/capture.json`, and the verbatim `tab create` stdout if the tab was made by the plugin.
  - If the `tab create` stdout is not JSON with `result.tab` and `result.root_pane`, fix `HerdrAdapter.tab_create` and its fixture before continuing.

- [ ] **M5 Search.** Type a word, pause, then type again quickly.
  - Expected: one request per pause. The list shows results for the latest text only. A query that returns 50 items shows `50+ matches — keep typing`.

- [ ] **M6 Create.** Press `prefix+c`, choose Create, enter `herdr sandbox create check`.
  - Expected: a sandbox ticket is created; the tab is labelled with its key. Run `/opt/homebrew/bin/atlas jira get <KEY> --site <SITE>` (read-only) and expect the summary and no body.

- [ ] **M7 Skip.** Press the `<FREE_CHORD>` chord (plain tab).
  - Expected: a tab with no `ticket:v1` label, and no ticket row for it (design Desired end state 8, row 5).

- [ ] **M8 Rename.** Rename a bound tab: `/Users/mason/.local/bin/herdr tab rename <TAB_ID> "renamed"`.
  - Expected: the marker is gone, the token is cleared, and the ticket row disappears (`tab.renamed`, D5).

- [ ] **M9 Restart.** Stop the `ticket-test` server and start it again.
  - Expected: the bound tab's label is back (from `session.json`), and the ticket row returns after the startup reconcile.
  - Record: how many snapshot attempts the startup took before a tab appeared (set D18 from it; the current bound is 20 attempts, 500 ms apart).
  - Token metadata is not restored (research Q4), so the row returns only through reconcile.

- [ ] **M10 Panes and display.** In a bound tab, run `claude` in the root pane. Split the pane and run `claude` in the second.
  - Expected: both agent panes show the key (design Desired end state 8, row 3).
  - A plain terminal in a bound tab shows no row (row 1, stated limit). A collapsed sidebar shows no row (row 4, stated limit).

- [ ] **M11 Site change.** Change `site` in `~/.config/herdr-ticket/config.toml` to another alias for the same Jira (for example the hostname). Restart the `ticket-test` server.
  - Expected: every marked tab loses its marker and its token. `pending` is cleared. `~/.config/herdr-ticket/ticket-test/state.json` records the new site (Desired end state 7).
  - Change `site` back afterwards, and rebind if needed.

- [ ] **M12 Recovery at each stage.** For each row, start the `ticket-test` server with `HERDR_TICKET_CRASH_AT=<point>` in its environment, trigger the action once (the picker exits with status 75 at that point), then restart the server without the variable and open the picker.

  | Point | Crash after | Expected on reopen |
  |---|---|---|
  | `creating` | write, before Jira | "Confirm…" with no candidates; discard works; no ticket exists in the sandbox |
  | `jira_call` | Jira create, before `jira_created` | candidate is the created key; confirm binds it; exactly one sandbox ticket with that summary |
  | `jira_created` | write | resumes, makes no second Jira create |
  | `tab_creating` | write, before tab | no matching tab; offer "new tab"; choosing it creates one tab |
  | `tab_call` | tab created, before `tab_created` | one match in the workspace is adopted without asking; after one reconcile the token is on every pane of that tab |
  | `tab_created` | write | token reported and `pending` cleared |

## Model change and sidebar check (2026-10-10)

- **Binding model:** the binding is the root pane's label (`ticket:v1 <KEY> · <TITLE>`). The tab label is the plain summary (commit 6aa7c03). Steps below that mention tab labels as the binding should be read with the pane label instead.
- **Sidebar check: pass (operator).** With `claude` running in a bound pane, the sidebar row showed the ticket key and status (`SDO-602 · In Progress`), and the tab name showed only the summary.
- **Status refresh:** `prefix+u` runs the reconcile action. Status is cached for five minutes per session, so a Jira change shows after the cache expires or after the cache is cleared.

## CLI results (ticket-test, run 2026-10-10 by the agent; picker and visual steps not run)

- **M8 Rename (CLI part): pass.** Renaming the tab removed the marker; reconcile cleared the `ticket` token. Restoring the marker and reconciling set it back. Row disappearance on screen not checked.
- **M9 Restart: pass.** The label persisted in `session.json` across `server stop` and start. Startup reconcile restored `ticket=SDO-602` on the bound pane. Startup attempts before a tab appeared: 1 (the tab was already in the snapshot), so D18's 20 attempts is not yet measured.
- **M11 Site change: pass.** With site changed, startup unbound the tab (marker removed, token cleared, label kept as the title). `state.json` recorded the new site. Config restored and startup re-run to set the site back.
- Not run: M4-M7 and M12 (need the picker TUI), M10 (needs agent panes; sidebar row not seen), M2/M3 (global, not agreed).

## M2 and M3 results (2026-10-10)

- **M2 Key: pass (partial).** `ctrl+b t` opened a plain tab (moved `new_tab` works). `ctrl+b c` returned an error because the plugin was not yet linked. Exact on-screen text not recorded. The server log has no entry for it. Config backup: `~/herdr-config-before-m2.toml`.
- **M3 Plugin: pass.** `herdr plugin link ~/src/herdr-ticket` succeeded. Actions `new-ticket-tab` and `reconcile` are listed. The manifest accepted the `pane.created` and `tab.renamed` events. Scope: the link is global. `default` also lists the plugin as enabled, so its events run in every session.

- [ ] **Gate.** The plugin works in the named session. Do not run any of M1–M12 against the normal Herdr session before this gate.
