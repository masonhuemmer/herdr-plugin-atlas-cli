package plugin

import (
	"fmt"
	"regexp"
	"strconv"
	"strings"
)

var (
	v1Marker = regexp.MustCompile(`^ticket:v1 ([A-Z][A-Z0-9]+-[0-9]+) · (.+)$`)
	v2Marker = regexp.MustCompile(`^ticket:v2 ([1-9][0-9]*)/([A-Z][A-Z0-9]+-[0-9]+) · (.+)$`)
	issueKey = regexp.MustCompile(`^[A-Z][A-Z0-9]+-[0-9]+$`)
)

type Binding struct {
	BoardID int
	Key     string
	Title   string
	Legacy  bool
}

func ParseMarker(label string) (Binding, bool) {
	if m := v2Marker.FindStringSubmatch(label); m != nil {
		id, err := strconv.Atoi(m[1])
		if err == nil && id > 0 {
			return Binding{BoardID: id, Key: m[2], Title: m[3]}, true
		}
	}
	if m := v1Marker.FindStringSubmatch(label); m != nil {
		return Binding{Key: m[1], Title: m[2], Legacy: true}, true
	}
	return Binding{}, false
}

func FormatMarker(b Binding) (string, error) {
	b.Key = strings.ToUpper(strings.TrimSpace(b.Key))
	b.Title = strings.TrimSpace(b.Title)
	if !issueKey.MatchString(b.Key) || b.BoardID <= 0 || b.Title == "" {
		return "", fmt.Errorf("binding requires issue key, board ID, and title")
	}
	return fmt.Sprintf("ticket:v2 %d/%s · %s", b.BoardID, b.Key, b.Title), nil
}
