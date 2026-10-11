package plugin

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"os/exec"
	"strconv"
	"strings"
	"time"
)

type Runner interface {
	Run(ctx context.Context, path string, args []string, stdin []byte) ([]byte, error)
}

type CommandRunner struct{}

func (CommandRunner) Run(ctx context.Context, path string, args []string, stdin []byte) ([]byte, error) {
	cmd := exec.CommandContext(ctx, path, args...)
	if stdin != nil {
		cmd.Stdin = bytes.NewReader(stdin)
	}
	var stdout, stderr bytes.Buffer
	cmd.Stdout, cmd.Stderr = &stdout, &stderr
	if err := cmd.Run(); err != nil {
		message := strings.TrimSpace(stderr.String())
		if message == "" {
			message = err.Error()
		}
		return nil, fmt.Errorf("%s: %s", path, message)
	}
	return stdout.Bytes(), nil
}

type Atlas struct {
	Path   string
	Site   string
	Runner Runner
}

func (a Atlas) CheckBoardSupport(ctx context.Context) error {
	ctx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()
	b, err := a.Runner.Run(ctx, a.Path, []string{"jira", "board", "--help"}, nil)
	if err != nil || !strings.Contains(string(b), "board placement") {
		return fmt.Errorf("Atlas lacks Jira board placement; install an Atlas build with board support")
	}
	if !strings.Contains(string(b), "suggest:") {
		return fmt.Errorf("Atlas lacks Jira issue suggestions; install an Atlas build with jira suggest support")
	}
	return nil
}

type Issue struct {
	Key       string `json:"key"`
	Summary   string `json:"summary"`
	Status    string `json:"status"`
	BrowseURL string `json:"browse_url"`
}

type SearchPage struct {
	Items         []Issue `json:"items"`
	NextPageToken string  `json:"next_page_token"`
	IsLast        bool    `json:"is_last"`
}

type Board struct {
	ID   int    `json:"id"`
	Name string `json:"name"`
	Type string `json:"type"`
}

type Placement struct {
	SchemaVersion int    `json:"schema_version"`
	BoardID       int    `json:"board_id"`
	BoardName     string `json:"board_name"`
	Site          string `json:"site"`
	Key           string `json:"key"`
	Summary       string `json:"summary"`
	BrowseURL     string `json:"browse_url"`
	Assignee      string `json:"assignee"`
	Status        string `json:"status"`
	StatusID      string `json:"status_id"`
	State         string `json:"state"`
	Column        string `json:"column"`
	OnBoard       bool   `json:"on_board"`
}

type Transition struct {
	ID         string `json:"id"`
	Name       string `json:"name"`
	ToStatus   string `json:"to_status"`
	ToStatusID string `json:"to_status_id"`
	Column     string `json:"column"`
}

func (a Atlas) call(ctx context.Context, out any, args ...string) error {
	ctx, cancel := context.WithTimeout(ctx, 35*time.Second)
	defer cancel()
	b, err := a.Runner.Run(ctx, a.Path, append([]string{"jira"}, args...), nil)
	if err != nil {
		return err
	}
	if err := json.Unmarshal(b, out); err != nil {
		return fmt.Errorf("atlas returned invalid JSON: %w", err)
	}
	return nil
}

func (a Atlas) Get(ctx context.Context, key string) (Issue, error) {
	var out Issue
	err := a.call(ctx, &out, "get", key, "--site", a.Site)
	return out, err
}

func (a Atlas) Search(ctx context.Context, jql string) ([]Issue, error) {
	var out struct {
		Items []Issue `json:"items"`
	}
	err := a.call(ctx, &out, "search", "--jql", jql, "--site", a.Site)
	return out.Items, err
}

func (a Atlas) SearchPage(ctx context.Context, jql string, limit int, pageToken string) (SearchPage, error) {
	args := []string{"search", "--jql", jql, "--limit", strconv.Itoa(limit), "--site", a.Site}
	if pageToken != "" {
		args = append(args, "--page-token", pageToken)
	}
	var out SearchPage
	err := a.call(ctx, &out, args...)
	return out, err
}

func (a Atlas) Suggest(ctx context.Context, query, project string) ([]Issue, error) {
	args := []string{"suggest", "--query", query, "--site", a.Site}
	if project != "" {
		args = append(args, "--project", project)
	}
	var out struct {
		Items []Issue `json:"items"`
	}
	err := a.call(ctx, &out, args...)
	return out.Items, err
}

func (a Atlas) Boards(ctx context.Context, project string) ([]Board, error) {
	args := []string{"boards", "--site", a.Site}
	if project != "" {
		args = append(args, "--project", project)
	}
	var out []Board
	err := a.call(ctx, &out, args...)
	return out, err
}

func (a Atlas) Placement(ctx context.Context, key string, boardID int) (Placement, error) {
	var out Placement
	err := a.call(ctx, &out, "board", "placement", key, "--board", strconv.Itoa(boardID), "--site", a.Site)
	if err == nil && out.SchemaVersion != 1 {
		err = fmt.Errorf("atlas board placement schema %d is unsupported; upgrade the plugin", out.SchemaVersion)
	}
	return out, err
}

func (a Atlas) Transitions(ctx context.Context, key string, boardID int) ([]Transition, error) {
	args := []string{"transitions", key, "--site", a.Site}
	if boardID > 0 {
		args = append(args, "--board", strconv.Itoa(boardID))
	}
	var out struct {
		Items []Transition `json:"items"`
	}
	err := a.call(ctx, &out, args...)
	return out.Items, err
}

func (a Atlas) Transition(ctx context.Context, key, name string) error {
	var out Issue
	return a.call(ctx, &out, "transition", key, "--name", name, "--site", a.Site)
}

func (a Atlas) TransitionID(ctx context.Context, key, id string) error {
	var out Issue
	return a.call(ctx, &out, "transition", key, "--id", id, "--site", a.Site)
}

func (a Atlas) Create(ctx context.Context, project, issueType, summary, assignee string) (Issue, error) {
	args := []string{"create", "--project", project, "--type", issueType, "--summary", summary, "--site", a.Site}
	if assignee != "" {
		args = append(args, "--assignee", assignee)
	}
	var out Issue
	err := a.call(ctx, &out, args...)
	return out, err
}

func (a Atlas) Comment(ctx context.Context, key, body string, internal bool) error {
	args := []string{"comment", key, "--body", body, "--site", a.Site}
	if internal {
		args = append(args, "--internal")
	}
	var out json.RawMessage
	return a.call(ctx, &out, args...)
}

type Pane struct {
	PaneID string `json:"pane_id"`
	TabID  string `json:"tab_id"`
	Label  string `json:"label"`
}

type Agent struct {
	PaneID       string            `json:"pane_id"`
	Status       string            `json:"agent_status"`
	AgentSession map[string]string `json:"agent_session"`
}

func (a Agent) SessionID() string { return a.AgentSession["value"] }

type Snapshot struct {
	Panes  []Pane  `json:"panes"`
	Agents []Agent `json:"agents"`
}

func (s Snapshot) Pane(id string) (Pane, bool) {
	for _, p := range s.Panes {
		if p.PaneID == id {
			return p, true
		}
	}
	return Pane{}, false
}

func (s Snapshot) Agent(id string) (Agent, bool) {
	for _, a := range s.Agents {
		if a.PaneID == id {
			return a, true
		}
	}
	return Agent{}, false
}

type Herdr struct {
	Path   string
	Runner Runner
}

func (h Herdr) call(ctx context.Context, out any, args ...string) error {
	ctx, cancel := context.WithTimeout(ctx, 15*time.Second)
	defer cancel()
	b, err := h.Runner.Run(ctx, h.Path, args, nil)
	if err != nil {
		return err
	}
	var envelope struct {
		Result json.RawMessage `json:"result"`
	}
	if err := json.Unmarshal(b, &envelope); err != nil || len(envelope.Result) == 0 {
		return fmt.Errorf("herdr returned invalid JSON")
	}
	return json.Unmarshal(envelope.Result, out)
}

func (h Herdr) Snapshot(ctx context.Context) (Snapshot, error) {
	var result struct {
		Snapshot Snapshot `json:"snapshot"`
	}
	err := h.call(ctx, &result, "api", "snapshot")
	return result.Snapshot, err
}

func (h Herdr) RenamePane(ctx context.Context, paneID, label string) error {
	var out any
	return h.call(ctx, &out, "pane", "rename", paneID, label)
}

func (h Herdr) ClearPaneLabel(ctx context.Context, paneID string) error {
	var out any
	return h.call(ctx, &out, "pane", "rename", paneID, "--clear")
}

func (h Herdr) Report(ctx context.Context, paneID string, tokens map[string]string) error {
	args := []string{"pane", "report-metadata", paneID, "--source", "herdr-ticket"}
	for _, key := range []string{"ticket", "ticket_summary", "ticket_column", "ticket_status"} {
		if value := tokens[key]; value != "" {
			args = append(args, "--token", key+"="+value)
		} else {
			args = append(args, "--clear-token", key)
		}
	}
	var out any
	return h.call(ctx, &out, args...)
}

func (h Herdr) OpenOverlay(ctx context.Context, entrypoint, paneID, workspace, cwd string) error {
	args := []string{"plugin", "pane", "open", "--plugin", PluginID, "--entrypoint", entrypoint,
		"--env", "HERDR_TICKET_TARGET_PANE_ID=" + paneID,
		"--env", "HERDR_TICKET_WORKSPACE_ID=" + workspace,
		"--env", "HERDR_TICKET_CWD=" + cwd}
	var out any
	return h.call(ctx, &out, args...)
}

func (h Herdr) TabCreate(ctx context.Context, workspace, cwd, label, ticketKey string) (string, error) {
	args := []string{"tab", "create", "--workspace", workspace, "--cwd", cwd, "--label", label, "--env", "FACTORY_TICKET=" + ticketKey, "--focus"}
	var out struct {
		RootPane struct {
			PaneID string `json:"pane_id"`
		} `json:"root_pane"`
	}
	if err := h.call(ctx, &out, args...); err != nil {
		return "", err
	}
	if out.RootPane.PaneID == "" {
		return "", fmt.Errorf("herdr created tab without root pane ID")
	}
	return out.RootPane.PaneID, nil
}

func (h Herdr) ReadPane(ctx context.Context, paneID string, idle bool) (string, error) {
	source := "visible"
	if idle {
		source = "recent-unwrapped"
	}
	var out struct {
		Read struct {
			Text string `json:"text"`
		} `json:"read"`
	}
	err := h.call(ctx, &out, "pane", "read", paneID, "--source", source, "--lines", "120", "--format", "text")
	return out.Read.Text, err
}
