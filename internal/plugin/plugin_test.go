package plugin

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"
)

func TestMarkerMigrationAndColor(t *testing.T) {
	legacy, ok := ParseMarker("ticket:v1 SDO-588 · Render descriptions")
	if !ok || !legacy.Legacy || legacy.BoardID != 0 {
		t.Fatalf("legacy marker: %+v %v", legacy, ok)
	}
	label, err := FormatMarker(Binding{BoardID: 42, Key: "sdo-588", Title: "Render descriptions"})
	if err != nil || label != "ticket:v2 42/SDO-588 · Render descriptions" {
		t.Fatalf("format %q: %v", label, err)
	}
	bound, ok := ParseMarker(label)
	if !ok || bound.BoardID != 42 || bound.Key != "SDO-588" {
		t.Fatalf("v2 marker: %+v", bound)
	}
	if _, ok := ParseMarker("ticket:v2 0/SDO-588 · Bad"); ok {
		t.Fatal("accepted board zero")
	}
	p := Placement{BoardID: 42, State: "in_column", Column: "Review"}
	if label := columnLabel(p, Config{}); !strings.Contains(label, "Review") {
		t.Fatal(label)
	}
	if label := columnLabel(p, Config{Colors: map[string]string{"42/Review": "🟣"}}); label != "🟣 Review" {
		t.Fatal(label)
	}
	p.State = "not_on_board"
	if columnLabel(p, Config{}) != "Not on board" {
		t.Fatal("off-board column was displayed")
	}
}

type fakeRunner struct {
	snapshot        Snapshot
	placements      map[string]Placement
	readText        string
	claude          int
	placement       int
	create          int
	createSuccess   bool
	transitionID    string
	commentCount    int
	commentInternal bool
	reports         map[string]map[string]string
	tabArgs         []string
}

func (f *fakeRunner) Run(_ context.Context, path string, args []string, stdin []byte) ([]byte, error) {
	if len(args) == 0 {
		return nil, fmt.Errorf("missing args")
	}
	if path == "go" {
		f.claude++
		if !strings.Contains(string(stdin), "SDO-1") || len(stdin) > 10000 {
			return nil, fmt.Errorf("draft evidence unbounded or missing issue")
		}
		return []byte("Completed the focused change; next run checks."), nil
	}
	if path == "herdr" {
		result := any(map[string]any{})
		switch {
		case len(args) > 1 && args[0] == "api" && args[1] == "snapshot":
			result = map[string]any{"snapshot": f.snapshot}
		case len(args) > 1 && args[0] == "pane" && args[1] == "read":
			result = map[string]any{"read": map[string]any{"text": f.readText}}
		case len(args) > 3 && args[0] == "pane" && args[1] == "rename":
			for i := range f.snapshot.Panes {
				if f.snapshot.Panes[i].PaneID == args[2] {
					f.snapshot.Panes[i].Label = args[3]
				}
			}
		case len(args) > 1 && args[0] == "pane" && args[1] == "report-metadata":
			if f.reports == nil {
				f.reports = map[string]map[string]string{}
			}
			tokens := map[string]string{}
			for i := 3; i+1 < len(args); i++ {
				if args[i] == "--token" {
					parts := strings.SplitN(args[i+1], "=", 2)
					tokens[parts[0]] = parts[1]
				}
			}
			f.reports[args[2]] = tokens
		case len(args) > 1 && args[0] == "tab" && args[1] == "create":
			f.tabArgs = append([]string(nil), args...)
			result = map[string]any{"root_pane": map[string]any{"pane_id": "w1:p2"}}
		}
		b, _ := json.Marshal(map[string]any{"result": result})
		return b, nil
	}
	if path == "atlas" {
		if len(args) >= 2 && args[0] == "jira" && args[1] == "create" {
			f.create++
			if f.createSuccess {
				return []byte(`{"key":"SDO-1","summary":"Work"}`), nil
			}
			return nil, fmt.Errorf("uncertain create result")
		}
		if len(args) >= 3 && args[0] == "jira" && args[1] == "get" {
			return []byte(`{"key":"SDO-1","summary":"Work"}`), nil
		}
		if len(args) >= 2 && args[0] == "jira" && args[1] == "transitions" {
			return []byte(`{"key":"SDO-1","items":[{"id":"71","name":"Move","to_status":"Doing","column":"Doing"},{"id":"72","name":"Move","to_status":"Done","column":"Done"}]}`), nil
		}
		if len(args) >= 2 && args[0] == "jira" && args[1] == "transition" {
			for i := range args {
				if args[i] == "--id" && i+1 < len(args) {
					f.transitionID = args[i+1]
				}
			}
			return []byte(`{"key":"SDO-1"}`), nil
		}
		if len(args) >= 2 && args[0] == "jira" && args[1] == "comment" {
			f.commentCount++
			for _, arg := range args {
				if arg == "--internal" {
					f.commentInternal = true
				}
			}
			return []byte(`{"key":"SDO-1"}`), nil
		}
		if len(args) >= 3 && args[0] == "jira" && args[1] == "board" && args[2] == "placement" {
			f.placement++
			p, ok := f.placements[args[3]]
			if !ok {
				return nil, fmt.Errorf("placement missing")
			}
			b, _ := json.Marshal(p)
			return b, nil
		}
	}
	return nil, fmt.Errorf("unexpected command %s %v", path, args)
}

func TestNewTicketTabSetsFactoryTicket(t *testing.T) {
	f := &fakeRunner{}
	paneID, err := (Herdr{Path: "herdr", Runner: f}).TabCreate(context.Background(), "w1", "/repo", "Work", "SDO-588")
	if err != nil || paneID != "w1:p2" {
		t.Fatalf("pane %q: %v", paneID, err)
	}
	for i := range f.tabArgs {
		if f.tabArgs[i] == "--env" && i+1 < len(f.tabArgs) && f.tabArgs[i+1] == "FACTORY_TICKET=SDO-588" {
			return
		}
	}
	t.Fatalf("missing ticket environment: %v", f.tabArgs)
}

func TestAttachingExistingTicketToNewTabPassesFactoryTicket(t *testing.T) {
	f := &fakeRunner{
		snapshot:   Snapshot{Panes: []Pane{{PaneID: "w1:p1"}, {PaneID: "w1:p2"}}},
		placements: map[string]Placement{"SDO-1": {SchemaVersion: 1, BoardID: 42, Key: "SDO-1", Summary: "Work", State: "in_column", Column: "Doing"}},
	}
	a := testApp(t, f)
	a.Env["HERDR_TICKET_WORKSPACE_ID"] = "w1"
	a.Env["HERDR_TICKET_CWD"] = "/repo"
	a.Config.Board = 42
	var out bytes.Buffer
	if err := a.Pick(context.Background(), NewScreen(strings.NewReader("SDO-1\nn\n"), &out)); err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(strings.Join(f.tabArgs, " "), "FACTORY_TICKET=SDO-1") {
		t.Fatalf("tab args %v", f.tabArgs)
	}
}

func TestCreatingTicketInNewTabPassesFactoryTicket(t *testing.T) {
	f := &fakeRunner{
		createSuccess: true,
		snapshot:      Snapshot{Panes: []Pane{{PaneID: "w1:p1"}, {PaneID: "w1:p2"}}},
		placements:    map[string]Placement{"SDO-1": {SchemaVersion: 1, BoardID: 42, Key: "SDO-1", Summary: "Work", State: "in_column", Column: "Doing"}},
	}
	a := testApp(t, f)
	a.Env["HERDR_TICKET_WORKSPACE_ID"] = "w1"
	a.Env["HERDR_TICKET_CWD"] = "/repo"
	a.Config.Project, a.Config.IssueType, a.Config.Board = "SDO", "Task", 42
	var out bytes.Buffer
	if err := a.Pick(context.Background(), NewScreen(strings.NewReader("+ Work\ny\nn\n"), &out)); err != nil {
		t.Fatal(err)
	}
	if f.create != 1 || !strings.Contains(strings.Join(f.tabArgs, " "), "FACTORY_TICKET=SDO-1") {
		t.Fatalf("creates %d, tab args %v", f.create, f.tabArgs)
	}
}

func testApp(t *testing.T, f *fakeRunner) *App {
	t.Helper()
	dir := t.TempDir()
	return &App{
		Env:    map[string]string{"HERDR_TICKET_TARGET_PANE_ID": "w1:p1"},
		Config: Config{Site: "dev", Claude: "go"},
		Atlas:  Atlas{Path: "atlas", Site: "dev", Runner: f},
		Herdr:  Herdr{Path: "herdr", Runner: f},
		Dir:    dir,
		Now:    func() time.Time { return time.Date(2026, 10, 10, 12, 0, 0, 0, time.UTC) },
	}
}

func TestSyncKeepsPerPaneColumnsAndVerifiesNewSession(t *testing.T) {
	f := &fakeRunner{
		snapshot: Snapshot{
			Panes:  []Pane{{PaneID: "w1:p1", Label: "ticket:v2 42/SDO-1 · First"}, {PaneID: "w1:p2", Label: "ticket:v2 42/SDO-2 · Second"}},
			Agents: []Agent{{PaneID: "w1:p1", Status: "working", AgentSession: map[string]string{"value": "session-1"}}},
		},
		placements: map[string]Placement{
			"SDO-1": {SchemaVersion: 1, BoardID: 42, Key: "SDO-1", Summary: "First", State: "in_column", Column: "Doing"},
			"SDO-2": {SchemaVersion: 1, BoardID: 42, Key: "SDO-2", Summary: "Second", State: "in_column", Column: "Review"},
		},
	}
	a := testApp(t, f)
	if err := a.Sync(context.Background(), false); err != nil {
		t.Fatal(err)
	}
	if f.placement != 2 || !strings.Contains(f.reports["w1:p1"]["ticket_column"], "Doing") || !strings.Contains(f.reports["w1:p2"]["ticket_column"], "Review") {
		t.Fatalf("wrong per-pane columns: %+v, calls=%d", f.reports, f.placement)
	}
	if err := a.Sync(context.Background(), false); err != nil || f.placement != 2 {
		t.Fatalf("cache missed: %v calls=%d", err, f.placement)
	}
	f.snapshot.Agents[0].AgentSession["value"] = "session-2"
	if err := a.Sync(context.Background(), false); err != nil || f.reports["w1:p1"]["ticket_column"] != "Verify ticket" {
		t.Fatalf("session change not flagged: %v %+v", err, f.reports["w1:p1"])
	}
}

func TestDraftMakesNoSecondModelCallWithoutNewEvidence(t *testing.T) {
	f := &fakeRunner{
		snapshot: Snapshot{
			Panes:  []Pane{{PaneID: "w1:p1", Label: "ticket:v2 42/SDO-1 · First"}},
			Agents: []Agent{{PaneID: "w1:p1", Status: "idle"}},
		},
		placements: map[string]Placement{"SDO-1": {SchemaVersion: 1, BoardID: 42, Key: "SDO-1", Site: "dev.atlassian.net", Summary: "First", State: "in_column", Column: "Doing"}},
		readText:   "Built feature\nRan tests",
	}
	a := testApp(t, f)
	var out bytes.Buffer
	if err := a.Draft(context.Background(), NewScreen(strings.NewReader("\n"), &out)); err != nil {
		t.Fatal(err)
	}
	if f.claude != 1 {
		t.Fatalf("model calls %d", f.claude)
	}
	out.Reset()
	if err := a.Draft(context.Background(), NewScreen(strings.NewReader("\n"), &out)); err != nil {
		t.Fatal(err)
	}
	if f.claude != 1 || !strings.Contains(out.String(), "Nothing new") {
		t.Fatalf("repeat draft called model: %d %s", f.claude, out.String())
	}
	state, err := readState(filepath.Join(a.Dir, "state.json"))
	if err != nil || len(state.DraftHashes) != 1 {
		t.Fatalf("draft fingerprint missing: %v %+v", err, state)
	}
}

func TestBrowseURLRejectsOtherHosts(t *testing.T) {
	p := Placement{Site: "dev.atlassian.net", Key: "SDO-1", BrowseURL: "https://evil.example/browse/SDO-1"}
	if _, err := validatedBrowseURL(p); err == nil {
		t.Fatal("accepted untrusted host")
	}
	p.BrowseURL = ""
	if got, err := validatedBrowseURL(p); err != nil || got != "https://dev.atlassian.net/browse/SDO-1" {
		t.Fatal(got, err)
	}
}

func TestEvidenceIsBoundedAndStable(t *testing.T) {
	raw := strings.Repeat("same\n", 2000) + "\x1b[31mDone\x1b[0m\n"
	norm := normalizeEvidence(raw)
	if len(norm) > 8192 || strings.Contains(norm, "\x1b") || !strings.HasSuffix(norm, "Done") {
		t.Fatalf("bad evidence normalization: %q", norm)
	}
	if evidenceHash(norm) != evidenceHash(normalizeEvidence(raw)) {
		t.Fatal("unstable fingerprint")
	}
	if normalizeEvidence("⠋ Building\n") != normalizeEvidence("⠙ Building\n") {
		t.Fatal("spinner animation changed evidence")
	}
}

func TestUncertainCreateNeverRetriesWithoutRecovery(t *testing.T) {
	f := &fakeRunner{
		snapshot:   Snapshot{Panes: []Pane{{PaneID: "w1:p1"}}},
		placements: map[string]Placement{"SDO-1": {SchemaVersion: 1, BoardID: 42, Key: "SDO-1", Summary: "Work", State: "in_column", Column: "Doing"}},
	}
	a := testApp(t, f)
	a.Config.Project, a.Config.IssueType, a.Config.Board = "SDO", "Task", 42
	var out bytes.Buffer
	err := a.Pick(context.Background(), NewScreen(strings.NewReader("+ Work\ny\n"), &out))
	if err == nil || f.create != 1 {
		t.Fatalf("create outcome %v, calls %d", err, f.create)
	}
	state, err := readState(filepath.Join(a.Dir, "state.json"))
	if err != nil || state.Pending == nil || state.Pending.Key != "" {
		t.Fatalf("missing uncertain pending: %v %+v", err, state.Pending)
	}
	out.Reset()
	if err := a.Pick(context.Background(), NewScreen(strings.NewReader("SDO-1\ny\n"), &out)); err != nil {
		t.Fatal(err, out.String())
	}
	if f.create != 1 || f.placement != 1 {
		t.Fatalf("recovery duplicated create or missed bind: create %d, placement %d", f.create, f.placement)
	}
	state, _ = readState(filepath.Join(a.Dir, "state.json"))
	if state.Pending != nil {
		t.Fatal("recovery did not clear pending")
	}
}

func TestTransitionMenuSelectsIDWhenNamesRepeat(t *testing.T) {
	f := &fakeRunner{
		snapshot:   Snapshot{Panes: []Pane{{PaneID: "w1:p1", Label: "ticket:v2 42/SDO-1 · Work"}}},
		placements: map[string]Placement{"SDO-1": {SchemaVersion: 1, BoardID: 42, Key: "SDO-1", Summary: "Work", State: "in_column", Column: "Done"}},
	}
	a := testApp(t, f)
	var out bytes.Buffer
	if err := a.TransitionMenu(context.Background(), NewScreen(strings.NewReader("2\ny\n"), &out)); err != nil {
		t.Fatal(err)
	}
	if f.transitionID != "72" {
		t.Fatalf("selected transition %q", f.transitionID)
	}
}

func TestDraftPostRequiresVisibilityAndIssueConfirmation(t *testing.T) {
	f := &fakeRunner{}
	a := testApp(t, f)
	b := Binding{Key: "SDO-1", Title: "Work", BoardID: 42}
	p := Placement{BoardID: 42, State: "in_column", Column: "Doing"}
	var out bytes.Buffer
	if err := a.reviewDraft(context.Background(), NewScreen(strings.NewReader("p\ni\nWRONG\n\n"), &out), b, p, "Progress"); err != nil {
		t.Fatal(err)
	}
	if f.commentCount != 0 {
		t.Fatal("posted without matching issue key")
	}
	out.Reset()
	if err := a.reviewDraft(context.Background(), NewScreen(strings.NewReader("p\ni\nSDO-1\n"), &out), b, p, "Progress"); err != nil {
		t.Fatal(err)
	}
	if f.commentCount != 1 || !f.commentInternal {
		t.Fatalf("internal note selection lost: count %d internal %v", f.commentCount, f.commentInternal)
	}
}

func TestConcurrentStateUpdatesPreserveEachEntry(t *testing.T) {
	dir := t.TempDir()
	var group sync.WaitGroup
	for i := 0; i < 12; i++ {
		group.Add(1)
		go func(i int) {
			defer group.Done()
			if err := updateState(dir, func(s *State) error {
				s.DraftHashes[fmt.Sprint(i)] = "saved"
				return nil
			}); err != nil {
				t.Errorf("state update %d: %v", i, err)
			}
		}(i)
	}
	group.Wait()
	state, err := readState(filepath.Join(dir, "state.json"))
	if err != nil || len(state.DraftHashes) != 12 {
		t.Fatalf("lost concurrent state updates: %v %+v", err, state.DraftHashes)
	}
}

func TestLegacyPythonPendingDescriptionCanBeRecovered(t *testing.T) {
	path := filepath.Join(t.TempDir(), "state.json")
	if err := os.WriteFile(path, []byte(`{"site":"dev","pending":{"stage":"jira_created","description":"Work","key":"SDO-1","workspace_id":"w1","cwd":"/tmp"}}`), 0600); err != nil {
		t.Fatal(err)
	}
	state, err := readState(path)
	if err != nil || state.Pending == nil || state.Pending.Summary != "Work" || state.Pending.Key != "SDO-1" {
		t.Fatalf("legacy pending lost: %v %+v", err, state.Pending)
	}
}
