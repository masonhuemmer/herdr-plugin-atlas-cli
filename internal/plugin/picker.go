package plugin

import (
	"context"
	"fmt"
	"os"
	"sort"
	"strings"
	"time"
	"unicode"
	"unicode/utf8"

	tea "github.com/charmbracelet/bubbletea"
	"golang.org/x/term"
)

func (s *Screen) Interactive() bool {
	in, inOK := s.Input.(*os.File)
	out, outOK := s.Out.(*os.File)
	return inOK && outOK && term.IsTerminal(int(in.Fd())) && term.IsTerminal(int(out.Fd()))
}

func initialPickerJQL(project string) string {
	filter := "assignee = currentUser() AND statusCategory != Done"
	if project != "" {
		filter = "project = " + project + " AND " + filter
	}
	return filter + " ORDER BY updated DESC"
}

func (a *App) pickInteractive(ctx context.Context, s *Screen) (Issue, string, bool, error) {
	page, loadErr := a.Atlas.SearchPage(ctx, initialPickerJQL(a.Config.Project), 50, "")
	projectFallback := false
	if loadErr == nil && len(page.Items) == 0 && a.Config.Project != "" {
		page, loadErr = a.Atlas.SearchPage(ctx, "project = "+a.Config.Project+" AND statusCategory != Done ORDER BY updated DESC", 50, "")
		projectFallback = true
	}
	m := &pickerModel{atlas: a.Atlas, project: a.Config.Project, recent: page.Items, projectFallback: projectFallback, width: 90}
	if loadErr != nil {
		m.message = "Recent tickets unavailable; type to search"
	}
	final, err := tea.NewProgram(m, tea.WithAltScreen(), tea.WithInput(s.Input), tea.WithOutput(s.Out)).Run()
	if err != nil {
		return Issue{}, "", false, err
	}
	result := final.(*pickerModel)
	return result.chosen, result.resultQuery, result.selectedIssue, nil
}

type pickerTick struct{ sequence int }
type pickerSuggestions struct {
	sequence int
	items    []Issue
	err      error
}

type pickerModel struct {
	atlas           Atlas
	project         string
	recent          []Issue
	projectFallback bool
	suggestions     []Issue
	query           string
	selected        int
	sequence        int
	width           int
	height          int
	message         string
	chosen          Issue
	resultQuery     string
	selectedIssue   bool
}

func (m *pickerModel) Init() tea.Cmd { return nil }

func (m *pickerModel) Update(message tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := message.(type) {
	case tea.WindowSizeMsg:
		m.width, m.height = msg.Width, msg.Height
	case pickerTick:
		if msg.sequence == m.sequence {
			query, sequence := strings.TrimSpace(m.query), m.sequence
			return m, func() tea.Msg {
				items, err := m.atlas.Suggest(context.Background(), query, m.project)
				return pickerSuggestions{sequence: sequence, items: items, err: err}
			}
		}
	case pickerSuggestions:
		if msg.sequence == m.sequence {
			m.suggestions = msg.items
			if msg.err != nil {
				m.message = "Jira suggestions unavailable; showing recent matches"
			} else {
				m.message = ""
			}
			m.clampSelection()
		}
	case tea.KeyMsg:
		switch msg.Type {
		case tea.KeyEsc, tea.KeyCtrlC:
			return m, tea.Quit
		case tea.KeyUp:
			if m.selected > 0 {
				m.selected--
			}
		case tea.KeyDown:
			if m.selected+1 < len(m.matches()) && m.selected+1 < m.visibleLimit() {
				m.selected++
			}
		case tea.KeyEnter:
			query := strings.TrimSpace(m.query)
			if strings.HasPrefix(query, "+") || issueKey.MatchString(strings.ToUpper(query)) {
				m.resultQuery = query
				return m, tea.Quit
			}
			matches := m.matches()
			if len(matches) > 0 {
				m.chosen = matches[m.selected]
				m.resultQuery = m.chosen.Key
				m.selectedIssue = true
				return m, tea.Quit
			}
		case tea.KeyBackspace, tea.KeyDelete:
			if m.query != "" {
				_, size := utf8.DecodeLastRuneInString(m.query)
				return m, m.changeQuery(m.query[:len(m.query)-size])
			}
		case tea.KeyCtrlU:
			return m, m.changeQuery("")
		case tea.KeySpace:
			return m, m.changeQuery(m.query + " ")
		case tea.KeyRunes:
			return m, m.changeQuery(m.query + string(msg.Runes))
		}
	}
	return m, nil
}

func (m *pickerModel) changeQuery(query string) tea.Cmd {
	if utf8.RuneCountInString(query) > 120 {
		return nil
	}
	m.query, m.selected, m.suggestions, m.message = query, 0, nil, ""
	m.sequence++
	if len([]rune(strings.TrimSpace(query))) < 2 || strings.HasPrefix(query, "+") {
		return nil
	}
	sequence := m.sequence
	return tea.Tick(300*time.Millisecond, func(time.Time) tea.Msg { return pickerTick{sequence: sequence} })
}

func (m *pickerModel) visibleLimit() int {
	if m.height > 0 && m.height < 16 {
		if m.height-6 < 1 {
			return 1
		}
		return m.height - 6
	}
	return 10
}

func (m *pickerModel) clampSelection() {
	limit := len(m.matches())
	if limit > m.visibleLimit() {
		limit = m.visibleLimit()
	}
	if m.selected >= limit {
		m.selected = 0
	}
}

func (m *pickerModel) matches() []Issue {
	query := strings.TrimSpace(m.query)
	if query == "" {
		return m.recent
	}
	if strings.HasPrefix(query, "+") {
		return nil
	}
	remote := map[string]bool{}
	seen := map[string]bool{}
	for _, issue := range m.suggestions {
		remote[issue.Key] = true
	}
	type scored struct {
		issue Issue
		score int
	}
	var ranked []scored
	for _, issue := range append(append([]Issue{}, m.recent...), m.suggestions...) {
		if seen[issue.Key] || issue.Key == "" {
			continue
		}
		seen[issue.Key] = true
		score := pickerScore(query, issue)
		if score == 0 && remote[issue.Key] {
			score = 1 // Jira may match text that is absent from the short summary.
		}
		if score > 0 {
			ranked = append(ranked, scored{issue: issue, score: score})
		}
	}
	sort.SliceStable(ranked, func(i, j int) bool { return ranked[i].score > ranked[j].score })
	out := make([]Issue, len(ranked))
	for i, item := range ranked {
		out[i] = item.issue
	}
	return out
}

func pickerScore(query string, issue Issue) int {
	key := strings.ToLower(issue.Key)
	summary := strings.ToLower(issue.Summary)
	total := 0
	for _, term := range strings.Fields(strings.ToLower(query)) {
		score := 0
		switch {
		case strings.HasPrefix(key, term):
			score = 100
		case strings.Contains(key, term):
			score = 80
		case strings.Contains(summary, term):
			score = 60
		default:
			for _, word := range strings.FieldsFunc(summary, func(r rune) bool { return !unicode.IsLetter(r) && !unicode.IsDigit(r) }) {
				if len([]rune(term)) >= 4 && editDistanceAtMostOne(term, word) {
					score = 30
					break
				}
				if subsequence(term, word) {
					score = 15
				}
			}
		}
		if score == 0 {
			return 0
		}
		total += score
	}
	return total
}

func subsequence(needle, haystack string) bool {
	letters := []rune(needle)
	if len(letters) < 2 {
		return false
	}
	index := 0
	for _, r := range haystack {
		if r == letters[index] {
			index++
			if index == len(letters) {
				return true
			}
		}
	}
	return false
}

func editDistanceAtMostOne(a, b string) bool {
	ar, br := []rune(a), []rune(b)
	if len(ar)-len(br) > 1 || len(br)-len(ar) > 1 {
		return false
	}
	i, j, edits := 0, 0, 0
	for i < len(ar) && j < len(br) {
		if ar[i] == br[j] {
			i, j = i+1, j+1
			continue
		}
		edits++
		if edits > 1 {
			return false
		}
		switch {
		case len(ar) > len(br):
			i++
		case len(br) > len(ar):
			j++
		default:
			i, j = i+1, j+1
		}
	}
	return edits+len(ar)-i+len(br)-j <= 1
}

func (m *pickerModel) View() string {
	var b strings.Builder
	fmt.Fprintln(&b, "Attach a Jira ticket")
	fmt.Fprintf(&b, "Search: %s█\n\n", terminalLine(m.query))
	if strings.HasPrefix(strings.TrimSpace(m.query), "+") {
		fmt.Fprintln(&b, "Press Enter to create a ticket with this summary.")
	} else {
		if strings.TrimSpace(m.query) == "" {
			if m.projectFallback {
				fmt.Fprintln(&b, "Recently updated active project tickets:")
			} else {
				fmt.Fprintln(&b, "Your recently updated active tickets:")
			}
		} else {
			fmt.Fprintln(&b, "Matches:")
		}
		matches := m.matches()
		limit := len(matches)
		if limit > m.visibleLimit() {
			limit = m.visibleLimit()
		}
		if limit == 0 {
			fmt.Fprintln(&b, "No matches yet")
		}
		for i := 0; i < limit; i++ {
			marker := "  "
			if i == m.selected {
				marker = "> "
			}
			line := fmt.Sprintf("%s%-10s %s", marker, matches[i].Key, terminalLine(matches[i].Summary))
			fmt.Fprintln(&b, truncateRunes(line, max(24, m.width-2)))
		}
	}
	if m.message != "" {
		fmt.Fprintf(&b, "\n%s\n", m.message)
	}
	fmt.Fprintln(&b, "\n↑/↓ select · Enter attach · Esc close · +summary create")
	return b.String()
}

func terminalLine(value string) string {
	return strings.Map(func(r rune) rune {
		if unicode.IsControl(r) {
			return -1
		}
		return r
	}, value)
}
