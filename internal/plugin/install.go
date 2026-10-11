package plugin

import (
	"context"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/pelletier/go-toml/v2"
)

const sidebarBlock = `[ui.sidebar.agents]
rows = [["state_icon", "agent", "workspace"], ["$ticket_summary"], ["$ticket", "$ticket_column"]]
`

const keyHints = `Suggested Herdr keybindings (choose free chords; existing bindings are never overwritten):

[[keys.command]]
key = "prefix+t"
type = "plugin_action"
command = "herdr-plugin-atlas-cli.new-ticket-tab"
description = "attach Jira ticket"

[[keys.command]]
key = "prefix+m"
type = "plugin_action"
command = "herdr-plugin-atlas-cli.set-status"
description = "transition Jira ticket"

[[keys.command]]
key = "prefix+u"
type = "plugin_action"
command = "herdr-plugin-atlas-cli.reconcile"
description = "refresh Jira context"

[[keys.command]]
key = "prefix+i"
type = "plugin_action"
command = "herdr-plugin-atlas-cli.ticket-detail"
description = "Jira ticket detail"

[[keys.command]]
key = "prefix+shift+u"
type = "plugin_action"
command = "herdr-plugin-atlas-cli.draft-update"
description = "draft Jira update"
`

func Install(env map[string]string, out io.Writer) error {
	config, err := LoadConfig(env)
	if err != nil {
		return err
	}
	atlasPath := firstNonempty(env["ATLAS_BIN_PATH"], config.Atlas, "atlas")
	if err := (Atlas{Path: atlasPath, Runner: CommandRunner{}}).CheckBoardSupport(context.Background()); err != nil {
		return err
	}
	path := env["HERDR_CONFIG_PATH"]
	if path == "" {
		if xdg := env["XDG_CONFIG_HOME"]; xdg != "" {
			path = filepath.Join(xdg, "herdr", "config.toml")
		} else {
			home, _ := os.UserHomeDir()
			path = filepath.Join(home, ".config", "herdr", "config.toml")
		}
	}
	content, err := os.ReadFile(path)
	if err != nil && !os.IsNotExist(err) {
		return err
	}
	var parsed map[string]any
	if len(content) > 0 {
		if err := toml.Unmarshal(content, &parsed); err != nil {
			return fmt.Errorf("Herdr config is invalid TOML: %w", err)
		}
	}
	ui, _ := parsed["ui"].(map[string]any)
	sidebar, _ := ui["sidebar"].(map[string]any)
	if sidebar != nil && sidebar["agents"] != nil {
		fmt.Fprintf(out, "Existing [ui.sidebar.agents] in %s was preserved. Set its rows to include:\n%s\n", path, sidebarBlock)
		fmt.Fprint(out, keyHints)
		return nil
	}
	updated := string(content)
	if updated != "" && !strings.HasSuffix(updated, "\n") {
		updated += "\n"
	}
	if updated != "" {
		updated += "\n"
	}
	updated += sidebarBlock
	var check map[string]any
	if err := toml.Unmarshal([]byte(updated), &check); err != nil {
		return fmt.Errorf("sidebar addition would make config invalid: %w", err)
	}
	fmt.Fprintf(out, "Appending to %s:\n%s", path, sidebarBlock)
	if len(content) > 0 {
		backup := fmt.Sprintf("%s.bak-%s", path, time.Now().Format("20060102150405"))
		file, err := os.OpenFile(backup, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0600)
		if err != nil {
			return err
		}
		if _, err := file.Write(content); err != nil {
			_ = file.Close()
			return err
		}
		if err := file.Close(); err != nil {
			return err
		}
		fmt.Fprintf(out, "Backup: %s\n", backup)
	}
	if err := os.MkdirAll(filepath.Dir(path), 0700); err != nil {
		return err
	}
	if err := os.WriteFile(path, []byte(updated), 0600); err != nil {
		return err
	}
	fmt.Fprint(out, keyHints)
	return nil
}
