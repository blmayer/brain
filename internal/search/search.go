package search

import (
	"encoding/json"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"
)

// MemoryKB holds all triplets in memory for fast searching
type MemoryKB struct {
	triplets   []Triplet
	mu         sync.RWMutex
	defsDir    string
	itensDir   string
}

// NewMemoryKB creates a new in-memory knowledge base
func NewMemoryKB() *MemoryKB {
	return &MemoryKB{
		triplets: make([]Triplet, 0),
	}
}

// Load loads all triplets from the defs and itens directories into memory
func (kb *MemoryKB) Load(defsDir, itensDir string) error {
	kb.mu.Lock()
	defer kb.mu.Unlock()

	kb.defsDir = defsDir
	kb.itensDir = itensDir
	kb.triplets = make([]Triplet, 0)

	// Load from defs directory
	if err := kb.loadFromDir(defsDir); err != nil {
		return fmt.Errorf("loading defs: %w", err)
	}

	// Load from itens directory
	if err := kb.loadFromDir(itensDir); err != nil {
		return fmt.Errorf("loading itens: %w", err)
	}

	logToFile("KB LOADED | Loaded %d triplet(s) into memory", len(kb.triplets))
	return nil
}

// loadFromDir recursively loads all JSON files from a directory
func (kb *MemoryKB) loadFromDir(dir string) error {
	return filepath.Walk(dir, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}

		if info.IsDir() || filepath.Ext(path) != ".json" {
			return nil
		}

		data, err := os.ReadFile(path)
		if err != nil {
			return nil // Skip unreadable files
		}

		// Try parsing as DefinitionList first (for defs/ files)
		var defList DefinitionList
		if err := json.Unmarshal(data, &defList); err == nil {
			if len(defList.Definitions) > 0 {
				for _, t := range defList.Definitions {
					t.Path = path
					kb.triplets = append(kb.triplets, t)
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
		kb.triplets = append(kb.triplets, t)
		return nil
	})
}

// Reload reloads the knowledge base from disk
func (kb *MemoryKB) Reload() error {
	return kb.Load(kb.defsDir, kb.itensDir)
}

// AddToMemory adds a triplet to the in-memory store
func (kb *MemoryKB) AddToMemory(t Triplet) {
	kb.mu.Lock()
	defer kb.mu.Unlock()

	kb.triplets = append(kb.triplets, t)
}

// Search searches the in-memory knowledge base
func (kb *MemoryKB) Search(q Query) []Triplet {
	kb.mu.RLock()
	defer kb.mu.RUnlock()

	// Normalize verb: strip trailing '?' for matching
	normalizedVerb := strings.TrimSuffix(q.Verb, "?")

	var results []Triplet
	for _, t := range kb.triplets {
		if matchesWithNormalizedVerb(q, t, normalizedVerb) {
			results = append(results, t)
		}
	}
	return results
}

// SearchWithLogging searches and logs the query
func (kb *MemoryKB) SearchWithLogging(q Query) []Triplet {
	// Log the query request
	logToFile("QUERY REQUEST | Subject: %s | Verb: %s | Object: %s | Context: %s | TemporalCtx: %s",
		q.Subject, q.Verb, q.Object, q.Context, q.TemporalCtx)

	results := kb.Search(q)

	// Log the query response
	tripletsJSON, _ := json.MarshalIndent(results, "", "  ")
	logToFile("QUERY RESPONSE | Found %d triplet(s): %s", len(results), string(tripletsJSON))

	return results
}

// Count returns the number of triplets in memory
func (kb *MemoryKB) Count() int {
	kb.mu.RLock()
	defer kb.mu.RUnlock()
	return len(kb.triplets)
}

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

	// Normalize verb: strip trailing '?' for matching
	normalizedVerb := strings.TrimSuffix(q.Verb, "?")

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
					if matchesWithNormalizedVerb(q, t, normalizedVerb) {
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
		if matchesWithNormalizedVerb(q, t, normalizedVerb) {
			results = append(results, t)
		}

		return nil
	})

	return results, err
}

// Global in-memory knowledge base instance
var globalKB *MemoryKB

// InitMemoryKB initializes and loads the global in-memory knowledge base
func InitMemoryKB(defsDir, itensDir string) error {
	globalKB = NewMemoryKB()
	return globalKB.Load(defsDir, itensDir)
}

// GetMemoryKB returns the global in-memory knowledge base
func GetMemoryKB() *MemoryKB {
	return globalKB
}

// KnowledgeBaseFromMemory searches the in-memory knowledge base
func KnowledgeBaseFromMemory(q Query) []Triplet {
	if globalKB == nil {
		return nil
	}
	return globalKB.SearchWithLogging(q)
}

// AddTripletToMemory adds a triplet to the global in-memory knowledge base
func AddTripletToMemory(t Triplet) {
	if globalKB != nil {
		globalKB.AddToMemory(t)
	}
}



func matchesWithNormalizedVerb(q Query, t Triplet, normalizedVerb string) bool {
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
	// Use normalized verb for matching (strip '?' from query)
	if normalizedVerb != "" && !strings.Contains(strings.ToLower(t.Verb), strings.ToLower(normalizedVerb)) {
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

// AddTriplet adds a new triplet to the knowledge base (both disk and memory)
func AddTriplet(triplet Triplet, defsDir, itensDir string) error {
	// Normalize verb: strip trailing '?' for consistent storage
	normalizedVerb := strings.TrimSuffix(triplet.Verb, "?")

	// Determine where to store based on verb
	var targetDir string
	var filename string

	// Check if it's a definition (verb is "is" or empty)
	if normalizedVerb == "is" || normalizedVerb == "" {
		targetDir = defsDir
		filename = fmt.Sprintf("%s.json", triplet.Subject)
	} else {
		// Store in nested hierarchy for relations
		targetDir = filepath.Join(itensDir, triplet.Subject, normalizedVerb)
		filename = fmt.Sprintf("%s.json", triplet.Object)

		// Create directory if it doesn't exist
		if err := os.MkdirAll(targetDir, 0755); err != nil {
			return err
		}
	}

	// Update triplet with normalized verb for storage
	triplet.Verb = normalizedVerb

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
			if err := writeJSON(path, defList); err != nil {
				return err
			}
		} else {
			// Fall back to single Triplet
			var existingTriplet Triplet
			if err := json.Unmarshal(data, &existingTriplet); err == nil {
				triplet.Path = path
				if err := writeJSON(path, triplet); err != nil {
					return err
				}
			}
		}
	} else {
		// New file - create it
		triplet.Path = path
		if err := writeJSON(path, triplet); err != nil {
			return err
		}
	}

	// Also add to in-memory knowledge base
	if globalKB != nil {
		globalKB.AddToMemory(triplet)
		logToFile("MEMORY ADD | Added triplet to memory: %s %s %s", triplet.Subject, triplet.Verb, triplet.Object)
	}

	return nil
}

// getLogFilePath returns the path to the log file in the XDG cache directory
func getLogFilePath() (string, error) {
	// Get XDG_CACHE_HOME, default to ~/.cache
	cacheHome := os.Getenv("XDG_CACHE_HOME")
	if cacheHome == "" {
		home, err := os.UserHomeDir()
		if err != nil {
			return "", err
		}
		cacheHome = filepath.Join(home, ".cache")
	}

	// Create brain cache directory if it doesn't exist
	cacheDir := filepath.Join(cacheHome, "brain")
	if err := os.MkdirAll(cacheDir, 0755); err != nil {
		return "", err
	}

	return filepath.Join(cacheDir, "knowledge.log"), nil
}

// logToFile writes a log message to the log file
func logToFile(format string, args ...interface{}) {
	logPath, err := getLogFilePath()
	if err != nil {
		log.Printf("Failed to get log file path: %v", err)
		return
	}

	msg := fmt.Sprintf(format, args...)
	logEntry := fmt.Sprintf("[%s] %s\n", time.Now().Format(time.RFC3339), msg)

	f, err := os.OpenFile(logPath, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
	if err != nil {
		log.Printf("Failed to open log file: %v", err)
		return
	}
	defer f.Close()

	if _, err := f.WriteString(logEntry); err != nil {
		log.Printf("Failed to write to log file: %v", err)
	}
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

	// Log the query request to local knowledge
	logToFile("QUERY REQUEST | Subject: %s | Verb: %s | Object: %s | Context: %s | TemporalCtx: %s",
		q.Subject, q.Verb, q.Object, q.Context, q.TemporalCtx)

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

	// Log the query response from local knowledge
	tripletsJSON, _ := json.MarshalIndent(allResults, "", "  ")
	logToFile("QUERY RESPONSE | Found %d triplet(s): %s", len(allResults), string(tripletsJSON))

	return allResults, nil
}
