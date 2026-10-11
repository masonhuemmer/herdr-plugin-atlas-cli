package plugin

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"time"
)

type CachedPlacement struct {
	Placement Placement `json:"placement"`
	At        time.Time `json:"at"`
}

type State struct {
	Site        string                     `json:"site"`
	Placements  map[string]CachedPlacement `json:"placements"`
	DraftHashes map[string]string          `json:"draft_hashes"`
	Sessions    map[string]string          `json:"sessions"`
	Pending     *PendingCreate             `json:"pending,omitempty"`
}

type PendingCreate struct {
	Summary     string `json:"summary"`
	Description string `json:"description,omitempty"` // Python v0.1 pending record
	Key         string `json:"key,omitempty"`
}

func readState(path string) (State, error) {
	s := State{Placements: map[string]CachedPlacement{}, DraftHashes: map[string]string{}, Sessions: map[string]string{}}
	b, err := os.ReadFile(path)
	if errors.Is(err, os.ErrNotExist) {
		return s, nil
	}
	if err != nil {
		return s, err
	}
	if err := json.Unmarshal(b, &s); err != nil {
		return State{}, fmt.Errorf("parse plugin state: %w", err)
	}
	if s.Placements == nil {
		s.Placements = map[string]CachedPlacement{}
	}
	if s.DraftHashes == nil {
		s.DraftHashes = map[string]string{}
	}
	if s.Sessions == nil {
		s.Sessions = map[string]string{}
	}
	if s.Pending != nil && s.Pending.Summary == "" {
		s.Pending.Summary = s.Pending.Description
	}
	return s, nil
}

// updateState serializes short file updates from concurrent Herdr event hooks.
func updateState(dir string, fn func(*State) error) error {
	if err := os.MkdirAll(dir, 0700); err != nil {
		return err
	}
	lockPath := filepath.Join(dir, "state.go.lock")
	deadline := time.Now().Add(5 * time.Second)
	for {
		f, err := os.OpenFile(lockPath, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0600)
		if err == nil {
			_ = f.Close()
			break
		}
		if !errors.Is(err, os.ErrExist) {
			return err
		}
		if info, statErr := os.Stat(lockPath); statErr == nil && time.Since(info.ModTime()) > 30*time.Second {
			_ = os.Remove(lockPath)
			continue
		}
		if time.Now().After(deadline) {
			return fmt.Errorf("plugin state is busy")
		}
		time.Sleep(40 * time.Millisecond)
	}
	defer os.Remove(lockPath)
	path := filepath.Join(dir, "state.json")
	s, err := readState(path)
	if err != nil {
		return err
	}
	if err := fn(&s); err != nil {
		return err
	}
	b, err := json.MarshalIndent(s, "", "  ")
	if err != nil {
		return err
	}
	tmp, err := os.CreateTemp(dir, "state-*.json")
	if err != nil {
		return err
	}
	defer os.Remove(tmp.Name())
	if err := tmp.Chmod(0600); err != nil {
		_ = tmp.Close()
		return err
	}
	if _, err := tmp.Write(b); err != nil {
		_ = tmp.Close()
		return err
	}
	if err := tmp.Close(); err != nil {
		return err
	}
	return os.Rename(tmp.Name(), path)
}

func placementKey(site string, b Binding) string {
	return fmt.Sprintf("%s/%d/%s", site, b.BoardID, b.Key)
}
