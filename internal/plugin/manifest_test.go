package plugin

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/pelletier/go-toml/v2"
)

func TestManifestUsesGoBinaryForAllEntrypoints(t *testing.T) {
	b, err := os.ReadFile(filepath.Join("..", "..", "herdr-plugin.toml"))
	if err != nil {
		t.Fatal(err)
	}
	var manifest struct {
		ID        string   `toml:"id"`
		Platforms []string `toml:"platforms"`
		Build     []struct {
			Command []string `toml:"command"`
		} `toml:"build"`
		Startup []struct {
			Command []string `toml:"command"`
		} `toml:"startup"`
		Actions []struct {
			ID      string   `toml:"id"`
			Command []string `toml:"command"`
		} `toml:"actions"`
		Panes []struct {
			ID      string   `toml:"id"`
			Command []string `toml:"command"`
		} `toml:"panes"`
		Events []struct {
			Command []string `toml:"command"`
		} `toml:"events"`
	}
	if err := toml.Unmarshal(b, &manifest); err != nil {
		t.Fatal(err)
	}
	if manifest.ID != PluginID || len(manifest.Platforms) != 3 || len(manifest.Build) != 1 || len(manifest.Actions) < 5 || len(manifest.Panes) < 4 {
		t.Fatalf("incomplete Go manifest: %+v", manifest)
	}
	if len(manifest.Build[0].Command) < 4 || manifest.Build[0].Command[0] != "go" || manifest.Build[0].Command[3] != "herdr-plugin-atlas-cli.exe" {
		t.Fatal("manifest does not build the Go executable")
	}
	for _, entry := range manifest.Startup {
		assertGoCommand(t, entry.Command)
	}
	for _, entry := range manifest.Actions {
		assertGoCommand(t, entry.Command)
	}
	for _, entry := range manifest.Panes {
		assertGoCommand(t, entry.Command)
	}
	for _, entry := range manifest.Events {
		assertGoCommand(t, entry.Command)
	}
}

func assertGoCommand(t *testing.T, command []string) {
	t.Helper()
	if len(command) != 2 || command[0] != "./herdr-plugin-atlas-cli.exe" {
		t.Fatalf("entrypoint does not use the Go executable: %v", command)
	}
}
