package plugin

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"strconv"
	"strings"
	"time"
)

type ActionTarget struct {
	PaneID    string
	Workspace string
	CWD       string
}

func actionTarget(env map[string]string) (ActionTarget, error) {
	var contextData struct {
		FocusedPaneID  string `json:"focused_pane_id"`
		FocusedPaneCWD string `json:"focused_pane_cwd"`
		WorkspaceID    string `json:"workspace_id"`
		WorkspaceCWD   string `json:"workspace_cwd"`
	}
	_ = json.Unmarshal([]byte(env["HERDR_PLUGIN_CONTEXT_JSON"]), &contextData)
	target := ActionTarget{
		PaneID:    firstNonempty(env["HERDR_TICKET_TARGET_PANE_ID"], contextData.FocusedPaneID, env["HERDR_ACTIVE_PANE_ID"], env["HERDR_PANE_ID"]),
		Workspace: firstNonempty(env["HERDR_TICKET_WORKSPACE_ID"], contextData.WorkspaceID, env["HERDR_WORKSPACE_ID"], env["HERDR_ACTIVE_WORKSPACE_ID"]),
		CWD:       firstNonempty(env["HERDR_TICKET_CWD"], contextData.FocusedPaneCWD, contextData.WorkspaceCWD, env["HERDR_ACTIVE_PANE_CWD"]),
	}
	if target.PaneID == "" {
		return target, fmt.Errorf("no focused pane in Herdr action context")
	}
	return target, nil
}

func (a *App) OpenAction(ctx context.Context, entrypoint string) error {
	target, err := actionTarget(a.Env)
	if err != nil {
		return err
	}
	return a.Herdr.OpenOverlay(ctx, entrypoint, target.PaneID, target.Workspace, target.CWD)
}

type Screen struct {
	Reader *bufio.Reader
	Out    io.Writer
}

func NewScreen(in io.Reader, out io.Writer) *Screen {
	return &Screen{Reader: bufio.NewReader(in), Out: out}
}

func (s *Screen) Ask(prompt string) (string, error) {
	_, _ = fmt.Fprint(s.Out, prompt)
	line, err := s.Reader.ReadString('\n')
	if err != nil && err != io.EOF {
		return "", err
	}
	return strings.TrimSpace(line), nil
}

func (s *Screen) Wait() {
	_, _ = s.Ask("\nPress Enter to close… ")
}

func (a *App) Pick(ctx context.Context, s *Screen) error {
	target, err := actionTarget(a.Env)
	if err != nil {
		return err
	}
	if handled, err := a.recoverPending(ctx, s, target); handled || err != nil {
		return err
	}
	fmt.Fprintln(s.Out, "Attach a Jira ticket to this pane")
	query, err := s.Ask("Issue key or search text (+summary to create, blank to cancel): ")
	if err != nil || query == "" {
		return err
	}
	var issue Issue
	if strings.HasPrefix(query, "+") {
		if a.Config.Project == "" || a.Config.IssueType == "" {
			return fmt.Errorf("create requires project and issue_type in plugin config")
		}
		summary := strings.TrimSpace(strings.TrimPrefix(query, "+"))
		if summary == "" {
			return fmt.Errorf("create requires a summary")
		}
		confirm, err := s.Ask(fmt.Sprintf("Create %s %s %q? [y/N] ", a.Config.Project, a.Config.IssueType, summary))
		if err != nil || !strings.EqualFold(confirm, "y") {
			return err
		}
		if err := updateState(a.Dir, func(st *State) error {
			if st.Pending != nil {
				return fmt.Errorf("resolve the pending ticket creation first")
			}
			st.Pending = &PendingCreate{Summary: summary}
			return nil
		}); err != nil {
			return err
		}
		issue, err = a.Atlas.Create(ctx, a.Config.Project, a.Config.IssueType, summary, a.Config.Assignee)
		if err != nil {
			return fmt.Errorf("create result is uncertain; pending recovery will not create a duplicate: %w", err)
		}
		if err := updateState(a.Dir, func(st *State) error {
			st.Pending.Key = issue.Key
			return nil
		}); err != nil {
			return fmt.Errorf("created %s; record its key before retrying: %w", issue.Key, err)
		}
		fmt.Fprintf(s.Out, "Created %s\n", issue.Key)
		if err := a.Atlas.Transition(ctx, issue.Key, "In Progress"); err != nil {
			fmt.Fprintf(s.Out, "Ticket created; In Progress transition was unavailable: %v\n", err)
		}
	} else if issueKey.MatchString(strings.ToUpper(query)) {
		issue, err = a.Atlas.Get(ctx, strings.ToUpper(query))
		if err != nil {
			return err
		}
	} else {
		matches, err := a.Atlas.Search(ctx, searchJQL(query))
		if err != nil {
			return err
		}
		if len(matches) == 0 {
			fmt.Fprintln(s.Out, "No Jira issues found")
			return nil
		}
		limit := len(matches)
		if limit > 20 {
			limit = 20
		}
		for i, item := range matches[:limit] {
			fmt.Fprintf(s.Out, "%2d  %s  %s  [%s]\n", i+1, item.Key, item.Summary, item.Status)
		}
		if len(matches) >= 50 {
			fmt.Fprintln(s.Out, "50+ matches; narrow your search if needed")
		}
		choice, err := s.Ask("Choose number (blank to cancel): ")
		if err != nil || choice == "" {
			return err
		}
		n, err := strconv.Atoi(choice)
		if err != nil || n < 1 || n > limit {
			return fmt.Errorf("invalid selection")
		}
		issue = matches[n-1]
	}
	boardID, err := a.chooseBoard(ctx, s, issue.Key)
	if err != nil {
		return err
	}
	binding := Binding{BoardID: boardID, Key: issue.Key, Title: issue.Summary}
	mode, err := s.Ask("Attach to focused pane [Enter] or open new ticket tab [n]? ")
	if err != nil {
		return err
	}
	paneID := target.PaneID
	if strings.EqualFold(mode, "n") {
		if target.Workspace == "" || target.CWD == "" {
			return fmt.Errorf("new tab needs workspace and cwd from Herdr action context")
		}
		paneID, err = a.Herdr.TabCreate(ctx, target.Workspace, target.CWD, issue.Summary)
		if err != nil {
			return err
		}
	}
	if err := a.bind(ctx, paneID, binding); err != nil {
		return fmt.Errorf("ticket %s selected; binding failed: %w", issue.Key, err)
	}
	if strings.HasPrefix(query, "+") {
		if err := updateState(a.Dir, func(st *State) error { st.Pending = nil; return nil }); err != nil {
			return err
		}
	}
	fmt.Fprintf(s.Out, "Bound %s to pane %s on board %d\n", issue.Key, paneID, boardID)
	return nil
}

func (a *App) recoverPending(ctx context.Context, s *Screen, target ActionTarget) (bool, error) {
	state, err := readState(a.Dir + string(os.PathSeparator) + "state.json")
	if err != nil || state.Pending == nil {
		return false, err
	}
	pending := state.Pending
	fmt.Fprintf(s.Out, "Pending Jira creation: %s\n", pending.Summary)
	key := pending.Key
	if key == "" {
		fmt.Fprintln(s.Out, "The prior create may have reached Jira before its key was saved. Check Jira before continuing; this action will not create another issue.")
		key, err = s.Ask("Enter the created issue key, or type DISCARD after checking Jira: ")
		if err != nil {
			return true, err
		}
	} else {
		choice, err := s.Ask(fmt.Sprintf("Recover %s [Enter], or type DISCARD after checking Jira: ", key))
		if err != nil {
			return true, err
		}
		if choice != "" {
			key = choice
		}
	}
	if strings.EqualFold(key, "DISCARD") {
		return true, updateState(a.Dir, func(st *State) error { st.Pending = nil; return nil })
	}
	key = strings.ToUpper(key)
	if !issueKey.MatchString(key) {
		return true, fmt.Errorf("pending creation kept; enter a valid issue key after checking Jira")
	}
	issue, err := a.Atlas.Get(ctx, key)
	if err != nil {
		return true, fmt.Errorf("pending creation kept: %w", err)
	}
	if !strings.EqualFold(issue.Summary, pending.Summary) {
		return true, fmt.Errorf("%s has a different summary; pending creation kept", key)
	}
	boardID, err := a.chooseBoard(ctx, s, key)
	if err != nil {
		return true, err
	}
	confirm, err := s.Ask(fmt.Sprintf("Attach recovered %s to focused pane %s? [y/N] ", key, target.PaneID))
	if err != nil || !strings.EqualFold(confirm, "y") {
		return true, err
	}
	if err := a.bind(ctx, target.PaneID, Binding{Key: key, Title: issue.Summary, BoardID: boardID}); err != nil {
		return true, err
	}
	if err := updateState(a.Dir, func(st *State) error { st.Pending = nil; return nil }); err != nil {
		return true, err
	}
	fmt.Fprintf(s.Out, "Recovered %s without another Jira create\n", key)
	return true, nil
}

func searchJQL(query string) string {
	query = strings.TrimSpace(strings.ReplaceAll(strings.ReplaceAll(query, "*", ""), "?", ""))
	query = strings.ReplaceAll(strings.ReplaceAll(query, "\\", "\\\\"), "\"", "\\\"")
	return `summary ~ "` + query + `*"`
}

func (a *App) chooseBoard(ctx context.Context, s *Screen, key string) (int, error) {
	if id := a.Config.BoardFor(key); id > 0 {
		return id, nil
	}
	project := strings.SplitN(key, "-", 2)[0]
	boards, err := a.Atlas.Boards(ctx, project)
	if err != nil {
		return 0, err
	}
	if len(boards) == 0 {
		return 0, fmt.Errorf("no Jira board found for %s; set board or [boards] in config", project)
	}
	if len(boards) == 1 {
		return boards[0].ID, nil
	}
	for i, board := range boards {
		fmt.Fprintf(s.Out, "%2d  %s (%s, ID %d)\n", i+1, board.Name, board.Type, board.ID)
	}
	choice, err := s.Ask("Choose board number: ")
	if err != nil {
		return 0, err
	}
	n, err := strconv.Atoi(choice)
	if err != nil || n < 1 || n > len(boards) {
		return 0, fmt.Errorf("invalid board selection")
	}
	return boards[n-1].ID, nil
}

func (a *App) placementFor(ctx context.Context, binding Binding, force bool) (Placement, time.Time, error) {
	if binding.BoardID == 0 {
		return Placement{}, time.Time{}, fmt.Errorf("legacy binding has no board; choose one in ticket detail")
	}
	key := placementKey(a.Config.Site, binding)
	state, err := readState(a.Dir + string(os.PathSeparator) + "state.json")
	if err != nil {
		return Placement{}, time.Time{}, err
	}
	cached, exists := state.Placements[key]
	if !force && exists && a.Now().Sub(cached.At) < 5*time.Minute {
		return cached.Placement, cached.At, nil
	}
	p, err := a.Atlas.Placement(ctx, binding.Key, binding.BoardID)
	if err != nil {
		if exists {
			return cached.Placement, cached.At, fmt.Errorf("board unavailable: %w", err)
		}
		return Placement{}, time.Time{}, err
	}
	at := a.Now()
	if err := updateState(a.Dir, func(s *State) error {
		s.Site = a.Config.Site
		s.Placements[key] = CachedPlacement{Placement: p, At: at}
		return nil
	}); err != nil {
		return Placement{}, time.Time{}, err
	}
	return p, at, nil
}

func (a *App) Detail(ctx context.Context, s *Screen) error {
	target, err := actionTarget(a.Env)
	if err != nil {
		return err
	}
	binding, snap, err := a.bindingForPane(ctx, target.PaneID)
	if err != nil {
		return err
	}
	if binding.Legacy {
		fmt.Fprintf(s.Out, "%s · %s\nLegacy binding needs a board.\n", binding.Key, binding.Title)
		boardID, err := a.chooseBoard(ctx, s, binding.Key)
		if err != nil {
			return err
		}
		binding.BoardID, binding.Legacy = boardID, false
		if err := a.bind(ctx, target.PaneID, binding); err != nil {
			return err
		}
	}
	for {
		p, at, fetchErr := a.placementFor(ctx, binding, false)
		if fetchErr != nil && p.Key == "" {
			return fetchErr
		}
		fmt.Fprintf(s.Out, "\n%s · %s\nBoard       %s (%d)\nColumn      %s\nJira status %s\nAssignee    %s\n", binding.Key, binding.Title,
			p.BoardName, p.BoardID, columnLabel(p, a.Config), p.Status, p.Assignee)
		if fetchErr != nil {
			fmt.Fprintf(s.Out, "Board data  stale (%v)\n", fetchErr)
		} else {
			fmt.Fprintf(s.Out, "Refreshed   %s\n", at.Format(time.RFC822))
		}
		if agent, ok := snap.Agent(target.PaneID); ok {
			fmt.Fprintf(s.Out, "Agent       %s\n", agent.Status)
			if agent.SessionID() == "" {
				fmt.Fprintln(s.Out, "Session     Unverified (Herdr has no session ID)")
			} else if st, err := readState(a.Dir + string(os.PathSeparator) + "state.json"); err == nil && st.Sessions[target.PaneID] != "" && st.Sessions[target.PaneID] != agent.SessionID() {
				fmt.Fprintln(s.Out, "Session     Verify ticket for this agent")
			}
		}
		browse, urlErr := validatedBrowseURL(p)
		if urlErr == nil {
			fmt.Fprintf(s.Out, "Jira URL    %s\n", browse)
		}
		choice, err := s.Ask("[o] Open here  [c] Copy link  [d] Draft update  [r] Refresh  [v] Verify ticket  [Enter] Close: ")
		if err != nil || choice == "" {
			return err
		}
		switch strings.ToLower(choice) {
		case "o":
			if urlErr != nil {
				fmt.Fprintln(s.Out, urlErr)
			} else if a.Config.Remote {
				fmt.Fprintln(s.Out, "Remote mode: copy this Jira URL to open it on your machine")
			} else if err := openBrowser(ctx, browse); err != nil {
				fmt.Fprintf(s.Out, "Open failed: %v\n", err)
			}
		case "c":
			if urlErr != nil {
				fmt.Fprintln(s.Out, urlErr)
			} else if err := copyClipboard(ctx, browse); err != nil {
				fmt.Fprintf(s.Out, "Clipboard unavailable; use URL above: %v\n", err)
			} else {
				fmt.Fprintln(s.Out, "Copied Jira URL")
			}
		case "d":
			return a.Draft(ctx, s)
		case "r":
			if _, _, err := a.placementFor(ctx, binding, true); err != nil {
				fmt.Fprintf(s.Out, "Refresh failed: %v\n", err)
			} else {
				_ = a.Sync(ctx, false)
			}
		case "v":
			if err := a.confirmSession(ctx, target.PaneID); err != nil {
				fmt.Fprintf(s.Out, "Could not verify: %v\n", err)
			}
		}
	}
}

func (a *App) TransitionMenu(ctx context.Context, s *Screen) error {
	target, err := actionTarget(a.Env)
	if err != nil {
		return err
	}
	binding, _, err := a.bindingForPane(ctx, target.PaneID)
	if err != nil {
		return err
	}
	items, err := a.Atlas.Transitions(ctx, binding.Key, binding.BoardID)
	if err != nil {
		return err
	}
	if len(items) == 0 {
		fmt.Fprintln(s.Out, "No transitions are currently available")
		return nil
	}
	fmt.Fprintf(s.Out, "Available transitions for %s\n", binding.Key)
	for i, item := range items {
		preview := item.ToStatus
		if item.Column != "" {
			preview += " → " + item.Column
		}
		fmt.Fprintf(s.Out, "%2d  %s  (%s)\n", i+1, item.Name, preview)
	}
	choice, err := s.Ask("Choose number (blank to cancel): ")
	if err != nil || choice == "" {
		return err
	}
	n, err := strconv.Atoi(choice)
	if err != nil || n < 1 || n > len(items) {
		return fmt.Errorf("invalid transition selection")
	}
	selected := items[n-1]
	confirm, err := s.Ask(fmt.Sprintf("Move %s through %q? [y/N] ", binding.Key, selected.Name))
	if err != nil || !strings.EqualFold(confirm, "y") {
		return err
	}
	if err := a.Atlas.TransitionID(ctx, binding.Key, selected.ID); err != nil {
		return err
	}
	return a.Sync(ctx, true)
}
