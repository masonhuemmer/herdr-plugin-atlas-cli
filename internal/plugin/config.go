package plugin

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/pelletier/go-toml/v2"
)

const PluginID = "herdr-plugin-atlas-cli"

type Config struct {
	Site      string            `toml:"site"`
	Project   string            `toml:"project"`
	IssueType string            `toml:"issue_type"`
	Assignee  string            `toml:"assignee"`
	Board     int               `toml:"board"`
	Boards    map[string]int    `toml:"boards"`
	Colors    map[string]string `toml:"colors"`
	Atlas     string            `toml:"atlas"`
	Herdr     string            `toml:"herdr"`
	Claude    string            `toml:"claude"`
	Remote    bool              `toml:"remote"`
}

func (c Config) BoardFor(key string) int {
	project := strings.SplitN(strings.ToUpper(key), "-", 2)[0]
	if id := c.Boards[project]; id > 0 {
		return id
	}
	return c.Board
}

func configDir(env map[string]string) string {
	if path := env["HERDR_PLUGIN_CONFIG_DIR"]; path != "" {
		return path
	}
	if path := env["XDG_CONFIG_HOME"]; path != "" {
		return filepath.Join(path, PluginID)
	}
	home, _ := os.UserHomeDir()
	return filepath.Join(home, ".config", PluginID)
}

func LoadConfig(env map[string]string) (Config, error) {
	path := filepath.Join(configDir(env), "config.toml")
	b, err := os.ReadFile(path)
	if err != nil {
		return Config{}, fmt.Errorf("read %s: %w", path, err)
	}
	var c Config
	if err := toml.Unmarshal(b, &c); err != nil {
		return Config{}, fmt.Errorf("parse %s: %w", path, err)
	}
	if strings.TrimSpace(c.Site) == "" {
		return Config{}, fmt.Errorf("%s requires site", path)
	}
	if c.Board < 0 {
		return Config{}, fmt.Errorf("board must be positive")
	}
	for project, id := range c.Boards {
		if id <= 0 || project != strings.ToUpper(project) {
			return Config{}, fmt.Errorf("boards entries require uppercase project keys and positive IDs")
		}
	}
	return c, nil
}

func stateDir(env map[string]string) string {
	base := env["HERDR_PLUGIN_STATE_DIR"]
	if base == "" {
		base = configDir(env)
	}
	name := "default"
	parts := strings.Split(filepath.ToSlash(env["HERDR_SOCKET_PATH"]), "/")
	for i, part := range parts {
		if part == "sessions" && i+1 < len(parts) && parts[i+1] != "" {
			name = parts[i+1]
		}
	}
	name = filepath.Base(name)
	return filepath.Join(base, name)
}

func EnvMap() map[string]string {
	m := map[string]string{}
	for _, item := range os.Environ() {
		parts := strings.SplitN(item, "=", 2)
		if len(parts) == 2 {
			m[parts[0]] = parts[1]
		}
	}
	return m
}
