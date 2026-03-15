package search

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

// Triplet represents a subject-verb-object triple
type Triplet struct {
	Subject    string   `json:"subject"`
	Verb       string   `json:"verb"`
	Object     string   `json:"object"`
	Confidence float64  `json:"confidence"`
	Source     string   `json:"source"`
	Date       string   `json:"date"`
	Path       string   `json:"path"`
	Context    string   `json:"context,omitempty"`
}

// DefinitionList represents a defs file containing multiple definitions for a subject
type DefinitionList struct {
	Subject     string     `json:"subject"`
	Definitions []Triplet  `json:"definitions"`
	Path        string     `json:"-"` // not serialized
}

// Query represents a search query
type Query struct {
	Subject     string
	Verb        string
	Object      string
	Context     string // optional context filter
	TemporalCtx string // temporal context for filtering
}

// Search looks for triplets matching the query in the knowledge base
func Search(root string, q Query) ([]Triplet, error) {
	var results []Triplet

	err := filepath.Walk(root, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}

		// Skip directories and non-json files
		if info.IsDir() || filepath.Ext(path) != ".json" {
			return nil
		}

		// Read and parse the file
		data, err := os.ReadFile(path)
		if err != nil {
			return nil // Skip unreadable files
		}

		// Try parsing as DefinitionList first (for defs/ files)
		var defList DefinitionList
		if err := json.Unmarshal(data, &defList); err == nil {
			// Check if this is a defs file (has definitions array)
			if len(defList.Definitions) > 0 {
				defList.Path = path
				for _, t := range defList.Definitions {
					t.Path = path
					if matches(q, t) {
						results = append(results, t)
					}
				}
				return nil
			}
		}

		// Fall back to single Triplet parsing (for itens/ files)
		var t Triplet
		if err := json.Unmarshal(data, &t); err != nil {
			return nil // Skip invalid JSON
		}

		t.Path = path

		// Match against query (empty fields match anything)
		if matches(q, t) {
			results = append(results, t)
		}

		return nil
	})

	return results, err
}

func matches(q Query, t Triplet) bool {
	// Check temporal context first
	if q.TemporalCtx != "" {
		if !matchesTemporal(t.Date, q.TemporalCtx) {
			return false
		}
	}

	// Check context filter
	if q.Context != "" {
		if !strings.Contains(strings.ToLower(t.Context), strings.ToLower(q.Context)) {
			return false
		}
	}

	// Check subject, verb, object
	if q.Subject != "" && !strings.Contains(strings.ToLower(t.Subject), strings.ToLower(q.Subject)) {
		return false
	}
	if q.Verb != "" && !strings.Contains(strings.ToLower(t.Verb), strings.ToLower(q.Verb)) {
		return false
	}
	if q.Object != "" && !strings.Contains(strings.ToLower(t.Object), strings.ToLower(q.Object)) {
		return false
	}
	return true
}

// matchesTemporal checks if a triplet's date matches the temporal context
func matchesTemporal(date string, temporalCtx string) bool {
	// Simple temporal matching logic
	// For now, we'll match based on date if temporalCtx is a year or date
	// Later can be enhanced with more sophisticated logic
	if temporalCtx == "present" || temporalCtx == "" {
		// Present tense - accept any date
		return true
	}
	if temporalCtx == "past" {
		// Past tense - accept any date (could add logic to prefer older dates)
		return true
	}
	// Check if temporalCtx contains the date
	return strings.Contains(strings.ToLower(date), strings.ToLower(temporalCtx))
}

// AddTriplet adds a new triplet to the knowledge base
func AddTriplet(triplet Triplet, defsDir, itensDir string) error {
	// Determine where to store based on verb
	var targetDir string
	var filename string

	// Check if it's a definition (verb is "is" or empty)
	if triplet.Verb == "is" || triplet.Verb == "" {
		targetDir = defsDir
		filename = fmt.Sprintf("%s.json", triplet.Subject)
	} else {
		// Store in nested hierarchy for relations
		targetDir = filepath.Join(itensDir, triplet.Subject, triplet.Verb)
		filename = fmt.Sprintf("%s.json", triplet.Object)

		// Create directory if it doesn't exist
		if err := os.MkdirAll(targetDir, 0755); err != nil {
			return err
		}
	}

	path := filepath.Join(targetDir, filename)

	// Check if file already exists
	if _, err := os.Stat(path); err == nil {
		// File exists - update it with new date/version
		data, err := os.ReadFile(path)
		if err != nil {
			return err
		}

		// Try to parse as DefinitionList first
		var defList DefinitionList
		if err := json.Unmarshal(data, &defList); err == nil && len(defList.Definitions) > 0 {
			// Update existing definition or add new one
			found := false
			for i := range defList.Definitions {
				if defList.Definitions[i].Verb == triplet.Verb && defList.Definitions[i].Object == triplet.Object {
					defList.Definitions[i] = triplet
					found = true
					break
				}
			}
			if !found {
				defList.Definitions = append(defList.Definitions, triplet)
			}
			return writeJSON(path, defList)
		}

		// Fall back to single Triplet
		var existingTriplet Triplet
		if err := json.Unmarshal(data, &existingTriplet); err == nil {
			triplet.Path = path
			return writeJSON(path, triplet)
		}
	} else {
		// New file - create it
		triplet.Path = path
		return writeJSON(path, triplet)
	}

	return nil
}

// writeJSON writes data to a JSON file
func writeJSON(path string, data interface{}) error {
	file, err := os.Create(path)
	if err != nil {
		return err
	}
	defer file.Close()

	encoder := json.NewEncoder(file)
	encoder.SetIndent("", "  ")
	return encoder.Encode(data)
}

// KnowledgeBase searches both defs and itens directories
func KnowledgeBase(defsDir, itensDir string, q Query) ([]Triplet, error) {
	var allResults []Triplet

	// Search defs directory
	defsResults, err := Search(defsDir, q)
	if err != nil {
		return nil, err
	}
	allResults = append(allResults, defsResults...)

	// Search itens directory
	itensResults, err := Search(itensDir, q)
	if err != nil {
		return nil, err
	}
	allResults = append(allResults, itensResults...)

	return allResults, nil
}
