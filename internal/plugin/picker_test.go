package plugin

import (
	"context"
	"fmt"
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"
)

func TestPickerShowsTenRecentTicketsAndUsesArrowSelection(t *testing.T) {
	m := &pickerModel{width: 90}
	for n := 1; n <= 12; n++ {
		m.recent = append(m.recent, Issue{Key: fmt.Sprintf("SDO-%d", n), Summary: "Recent work"})
	}
	view := m.View()
	if !strings.Contains(view, "SDO-10") || strings.Contains(view, "SDO-11") {
		t.Fatal(view)
	}
	for range 12 {
		m.Update(tea.KeyMsg{Type: tea.KeyDown})
	}
	if m.selected != 9 {
		t.Fatalf("selected %d", m.selected)
	}
	m.Update(tea.KeyMsg{Type: tea.KeyEnter})
	if !m.selectedIssue || m.chosen.Key != "SDO-10" {
		t.Fatalf("chosen %+v", m.chosen)
	}
}

func TestPickerFuzzyTypoAndExactKey(t *testing.T) {
	m := &pickerModel{recent: []Issue{{Key: "SDO-588", Summary: "Provision SES UAT"}, {Key: "SDO-100", Summary: "Other work"}}}
	m.changeQuery("provison")
	matches := m.matches()
	if len(matches) != 1 || matches[0].Key != "SDO-588" {
		t.Fatalf("fuzzy matches %+v", matches)
	}
	m.changeQuery("SDO-999")
	m.Update(tea.KeyMsg{Type: tea.KeyEnter})
	if m.resultQuery != "SDO-999" || m.selectedIssue {
		t.Fatalf("exact key %q selected=%v", m.resultQuery, m.selectedIssue)
	}
	m.changeQuery("+Create a new task")
	m.Update(tea.KeyMsg{Type: tea.KeyEnter})
	if m.resultQuery != "+Create a new task" || m.selectedIssue {
		t.Fatalf("create %q selected=%v", m.resultQuery, m.selectedIssue)
	}
}

type pickerRunner struct{ calls int }

func (r *pickerRunner) Run(_ context.Context, _ string, args []string, _ []byte) ([]byte, error) {
	if len(args) < 3 || args[0] != "jira" || args[1] != "suggest" {
		return nil, fmt.Errorf("unexpected args %v", args)
	}
	r.calls++
	return []byte(`{"items":[{"key":"SDO-900","summary":"Provision a remote issue"}]}`), nil
}

func TestPickerDebouncesAndIgnoresStaleSuggestions(t *testing.T) {
	runner := &pickerRunner{}
	m := &pickerModel{atlas: Atlas{Path: "atlas", Site: "dev", Runner: runner}, recent: []Issue{{Key: "SDO-1", Summary: "Other"}}}
	if cmd := m.changeQuery("pro"); cmd == nil || runner.calls != 0 {
		t.Fatalf("suggestion call happened before debounce: %d", runner.calls)
	}
	oldSequence := m.sequence
	m.changeQuery("prov")
	_, stale := m.Update(pickerTick{sequence: oldSequence})
	if stale != nil || runner.calls != 0 {
		t.Fatal("stale debounce started a request")
	}
	_, search := m.Update(pickerTick{sequence: m.sequence})
	if search == nil || runner.calls != 0 {
		t.Fatal("search ran before command execution")
	}
	result := search()
	m.Update(result)
	if runner.calls != 1 || len(m.matches()) != 1 || m.matches()[0].Key != "SDO-900" {
		t.Fatalf("calls %d matches %+v", runner.calls, m.matches())
	}
	m.changeQuery("other")
	m.Update(result)
	if len(m.suggestions) != 0 {
		t.Fatal("stale result replaced new query")
	}
}

func TestPickerSanitizesJiraTerminalText(t *testing.T) {
	if got := terminalLine("Issue\x1b[2J\nTitle"); got != "Issue[2JTitle" {
		t.Fatal(got)
	}
	if got := initialPickerJQL("SDO"); !strings.Contains(got, "project = SDO") || !strings.Contains(got, "assignee = currentUser()") {
		t.Fatal(got)
	}
}
