# Herdr Atlas plugin agent instructions

Use the same working rules supplied for Atlas CLI:

1. State assumptions and tradeoffs before changing behavior. Ask when an essential requirement is unclear.
2. Implement the smallest solution that meets the requested behavior. Avoid speculative options and abstractions.
3. Keep edits surgical. Preserve existing conventions and remove only code made obsolete by the change.
4. Define observable success criteria, verify them, and stop optional testing once the relevant risks are covered.

The plugin owns Herdr pane bindings, display metadata, browser actions, and on-demand drafts. Atlas owns Jira authentication and the JSON board, issue, transition, and comment commands. Keep Jira credentials in Atlas. Treat an unavailable board read as unknown placement; never turn it into a confirmed column or off-board result.

The Herdr plugin ID is `herdr-plugin-atlas-cli`. Preserve it so installed actions and keybindings keep their identity. The Atlas board placement JSON contract is schema version 1; update both repositories together when changing that contract.
