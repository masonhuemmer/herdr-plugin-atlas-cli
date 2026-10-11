package plugin

import (
	"context"
	"fmt"
	"hash/fnv"
	"net/url"
	"os"
	"os/exec"
	"runtime"
	"strings"
	"time"
	"unicode/utf8"
)

type App struct {
	Env    map[string]string
	Config Config
	Atlas  Atlas
	Herdr  Herdr
	Dir    string
	Now    func() time.Time
}

func NewApp(env map[string]string, runner Runner) (*App, error) {
	c, err := LoadConfig(env)
	if err != nil {
		return nil, err
	}
	if runner == nil {
		runner = CommandRunner{}
	}
	atlasPath := firstNonempty(env["ATLAS_BIN_PATH"], c.Atlas, "atlas")
	herdrPath := firstNonempty(env["HERDR_BIN_PATH"], c.Herdr, "herdr")
	if _, err := exec.LookPath(atlasPath); err != nil {
		return nil, fmt.Errorf("Atlas executable %q not found; set atlas in plugin config or ATLAS_BIN_PATH", atlasPath)
	}
	if _, err := exec.LookPath(herdrPath); err != nil {
		return nil, fmt.Errorf("Herdr executable %q not found; set HERDR_BIN_PATH", herdrPath)
	}
	return &App{Env: env, Config: c, Atlas: Atlas{Path: atlasPath, Site: c.Site, Runner: runner},
		Herdr: Herdr{Path: herdrPath, Runner: runner}, Dir: stateDir(env), Now: time.Now}, nil
}

func firstNonempty(values ...string) string {
	for _, value := range values {
		if value != "" {
			return value
		}
	}
	return ""
}

func (a *App) Start(ctx context.Context) error {
	if err := a.Atlas.CheckBoardSupport(ctx); err != nil {
		return err
	}
	// Restored panes can appear after the plugin startup hook fires.
	for attempt := 0; attempt < 20; attempt++ {
		snap, err := a.Herdr.Snapshot(ctx)
		if err == nil && len(snap.Panes) > 0 {
			return a.syncSnapshot(ctx, snap, false)
		}
		if attempt == 19 {
			if err != nil {
				return err
			}
			return nil
		}
		time.Sleep(500 * time.Millisecond)
	}
	return nil
}

func (a *App) Sync(ctx context.Context, force bool) error {
	snap, err := a.Herdr.Snapshot(ctx)
	if err != nil {
		return err
	}
	return a.syncSnapshot(ctx, snap, force)
}

func (a *App) syncSnapshot(ctx context.Context, snap Snapshot, force bool) error {
	path := a.Dir + string(os.PathSeparator) + "state.json"
	state, err := readState(path)
	if err != nil {
		return err
	}
	if state.Site != "" && state.Site != a.Config.Site {
		for _, p := range snap.Panes {
			if _, bound := ParseMarker(p.Label); bound {
				if err := a.Herdr.ClearPaneLabel(ctx, p.PaneID); err != nil {
					return err
				}
			}
			if err := a.Herdr.Report(ctx, p.PaneID, nil); err != nil {
				return err
			}
		}
		return updateState(a.Dir, func(s *State) error {
			*s = State{Site: a.Config.Site, Placements: map[string]CachedPlacement{}, DraftHashes: map[string]string{}, Sessions: map[string]string{}}
			return nil
		})
	}
	updated := map[string]CachedPlacement{}
	newSessions := map[string]string{}
	for _, p := range snap.Panes {
		binding, bound := ParseMarker(p.Label)
		if !bound {
			if err := a.Herdr.Report(ctx, p.PaneID, nil); err != nil {
				return err
			}
			continue
		}
		tokens := map[string]string{"ticket": binding.Key, "ticket_summary": truncateRunes(binding.Title, 80)}
		if binding.Legacy || binding.BoardID == 0 {
			tokens["ticket_column"] = "Select board"
		} else {
			cacheKey := placementKey(a.Config.Site, binding)
			cached, exists := updated[cacheKey]
			if !exists {
				cached, exists = state.Placements[cacheKey]
			}
			if force || !exists || a.Now().Sub(cached.At) >= 5*time.Minute {
				placement, fetchErr := a.Atlas.Placement(ctx, binding.Key, binding.BoardID)
				if fetchErr == nil {
					cached = CachedPlacement{Placement: placement, At: a.Now()}
					updated[cacheKey] = cached
					exists = true
				} else {
					fmt.Fprintf(os.Stderr, "%s: placement for %s: %v\n", PluginID, binding.Key, fetchErr)
					if exists {
						cached.At = time.Time{} // show stale until the next successful read
						updated[cacheKey] = cached
					}
				}
			}
			if !exists {
				tokens["ticket_column"] = "Board unavailable"
			} else if cached.At.IsZero() {
				tokens["ticket_column"] = "Stale · " + columnLabel(cached.Placement, a.Config)
			} else {
				tokens["ticket_column"] = columnLabel(cached.Placement, a.Config)
			}
			if exists {
				tokens["ticket_status"] = cached.Placement.Status
				if cached.Placement.Summary != "" {
					tokens["ticket_summary"] = truncateRunes(cached.Placement.Summary, 80)
				}
			}
		}
		if agent, ok := snap.Agent(p.PaneID); ok && agent.SessionID() != "" {
			if prior := state.Sessions[p.PaneID]; prior != "" && prior != agent.SessionID() {
				tokens["ticket_column"] = "Verify ticket"
			} else if prior == "" {
				newSessions[p.PaneID] = agent.SessionID()
			}
		}
		tokens["ticket_column"] = truncateRunes(tokens["ticket_column"], 80)
		if err := a.Herdr.Report(ctx, p.PaneID, tokens); err != nil {
			return err
		}
	}
	return updateState(a.Dir, func(s *State) error {
		if s.Site != a.Config.Site {
			s.Site = a.Config.Site
		}
		for key, value := range updated {
			s.Placements[key] = value
		}
		for key, value := range newSessions {
			if s.Sessions[key] == "" {
				s.Sessions[key] = value
			}
		}
		return nil
	})
}

func truncateRunes(value string, max int) string {
	if utf8.RuneCountInString(value) <= max {
		return value
	}
	r := []rune(value)
	return string(r[:max-1]) + "…"
}

var columnDots = []string{"🔵", "🟡", "🟢", "🟣", "🟠", "🔴", "⚪"}

func columnLabel(p Placement, c Config) string {
	switch p.State {
	case "in_column":
		if p.Column == "" {
			return "Unmapped status"
		}
		key := fmt.Sprintf("%d/%s", p.BoardID, p.Column)
		if override := c.Colors[key]; override != "" {
			return override + " " + p.Column
		}
		h := fnv.New32a()
		_, _ = h.Write([]byte(key))
		return columnDots[int(h.Sum32())%len(columnDots)] + " " + p.Column
	case "not_on_board":
		return "Not on board"
	default:
		return "Unmapped status"
	}
}

func (a *App) bindingForPane(ctx context.Context, paneID string) (Binding, Snapshot, error) {
	snap, err := a.Herdr.Snapshot(ctx)
	if err != nil {
		return Binding{}, Snapshot{}, err
	}
	p, ok := snap.Pane(paneID)
	if !ok {
		return Binding{}, snap, fmt.Errorf("pane %s not found", paneID)
	}
	b, ok := ParseMarker(p.Label)
	if !ok {
		return Binding{}, snap, fmt.Errorf("pane %s has no bound Jira ticket", paneID)
	}
	return b, snap, nil
}

func (a *App) bind(ctx context.Context, paneID string, b Binding) error {
	label, err := FormatMarker(b)
	if err != nil {
		return err
	}
	if err := a.Herdr.RenamePane(ctx, paneID, label); err != nil {
		return err
	}
	snap, err := a.Herdr.Snapshot(ctx)
	if err == nil {
		if pane, ok := snap.Pane(paneID); ok && pane.TabID != "" {
			count, err := a.Herdr.TabPaneCount(ctx, pane.TabID)
			if err != nil {
				return err
			}
			if count == 1 {
				if err := a.Herdr.RenameTab(ctx, pane.TabID, truncateRunes(b.Key+" · "+b.Title, 80)); err != nil {
					return err
				}
			}
		}
		if agent, ok := snap.Agent(paneID); ok && agent.SessionID() != "" {
			_ = updateState(a.Dir, func(s *State) error { s.Sessions[paneID] = agent.SessionID(); return nil })
		}
	}
	return a.Sync(ctx, true)
}

func (a *App) confirmSession(ctx context.Context, paneID string) error {
	snap, err := a.Herdr.Snapshot(ctx)
	if err != nil {
		return err
	}
	agent, ok := snap.Agent(paneID)
	if !ok || agent.SessionID() == "" {
		return fmt.Errorf("Herdr has no session ID for this pane")
	}
	if err := updateState(a.Dir, func(s *State) error { s.Sessions[paneID] = agent.SessionID(); return nil }); err != nil {
		return err
	}
	return a.Sync(ctx, false)
}

func validatedBrowseURL(p Placement) (string, error) {
	if !issueKey.MatchString(p.Key) || p.Site == "" {
		return "", fmt.Errorf("placement has no valid Jira key or site")
	}
	raw := p.BrowseURL
	if raw == "" {
		raw = "https://" + p.Site + "/browse/" + p.Key
	}
	u, err := url.Parse(raw)
	if err != nil || u.Scheme != "https" || !strings.EqualFold(u.Hostname(), p.Site) || u.Path != "/browse/"+p.Key || u.User != nil {
		return "", fmt.Errorf("Jira browse URL does not match the configured site and issue")
	}
	return u.String(), nil
}

func openBrowser(ctx context.Context, rawURL string) error {
	var name string
	var args []string
	switch runtime.GOOS {
	case "darwin":
		name, args = "open", []string{rawURL}
	case "windows":
		name, args = "rundll32.exe", []string{"url.dll,FileProtocolHandler", rawURL}
	default:
		name, args = "xdg-open", []string{rawURL}
	}
	return exec.CommandContext(ctx, name, args...).Run()
}

func copyClipboard(ctx context.Context, value string) error {
	var name string
	var args []string
	switch runtime.GOOS {
	case "darwin":
		name = "pbcopy"
	case "windows":
		name, args = "powershell.exe", []string{"-NoProfile", "-Command", "Set-Clipboard -Value ([Console]::In.ReadToEnd())"}
	default:
		if _, err := exec.LookPath("wl-copy"); err == nil {
			name = "wl-copy"
		} else {
			name, args = "xclip", []string{"-selection", "clipboard"}
		}
	}
	cmd := exec.CommandContext(ctx, name, args...)
	cmd.Stdin = strings.NewReader(value)
	return cmd.Run()
}
