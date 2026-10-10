# Sandbox create check (operator step)

**Status: PENDING — not yet run.** The agent does not run this; it writes to Jira.

## Command

Choose `<SANDBOX_PROJECT>` and `<SITE>` (an atlas site alias from `atlas site list`), then run:

```sh
/opt/homebrew/bin/atlas jira create --project <SANDBOX_PROJECT> --type Task --summary "herdr-ticket sandbox create check" --site <SITE>
```

Then confirm the issue:

```sh
/opt/homebrew/bin/atlas jira get <KEY> --site <SITE>
```

## Record here

- Date and time of the run:
- `<SANDBOX_PROJECT>`:
- `<SITE>`:
- Exit code:
- Stdout, verbatim (the success output, with the new issue key):
- Stderr, verbatim (empty on success):
- Required fields beyond `--project`, `--type`, `--summary`, if any (record them and stop; design Decision 7 is then false):
- Did the create use the configured default assignee when `--assignee` was omitted? (The dry run echoed an assignee with no `--assignee` flag, so a default is set in config. Record whether the real create assigns it.)
- Output of `atlas jira get <KEY>`, summary line only:

## After recording

If the stdout is not JSON with a `key` field, update `AtlasJira.create` and `tests/contract/fixtures/jira_dry_run_create.json` to the recorded shape, then run `.venv/bin/python -m pytest -q tests/contract`. Tick the Phase 3 manual items in `plan.md`.

## Result (recorded 2026-10-10)
Command: `atlas jira create --project SDO --type Task --summary "[TEST] herdr-ticket sandbox create - safe to close" --site sesamidevel`
Created **SDO-602** (test ticket, safe to close; not a sandbox project, it is SDO).
Output shape (exit 0):
`{"key","site","browse_url","summary","status","issuetype","priority","assignee","reporter","created","updated","project"}`
Status on creation: `To Do`. The `key` field is present, so `create` returns it.
