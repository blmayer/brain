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
    triplets []Triplet
    kbDir    string
    mu       sync.RWMutex
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

// DefinitionList represents a list of definitions
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

// NewMemoryKB creates a new in-memory knowledge base
func NewMemoryKB() *MemoryKB {
    return &MemoryKB{
        triplets: []Triplet{},
        kbDir:    "", // Will be set by Load
    }
}

// Load loads all triplets from the kb directory into memory
func (kb *MemoryKB) Load(kbDir string) error {
    kb.triplets = kb.triplets[:0] // Reset triplets
    kb.kbDir = kbDir

    // Walk through the kb directory
    err := filepath.Walk(kbDir, func(path string, info os.FileInfo, err error) error {
        if err != nil {
            return err
        }

        // Skip directories and non-json files
        if info.IsDir() || filepath.Ext(path) != ".json" {
            return nil
        }

        data, err := os.ReadFile(path)
        if err != nil {
            return nil // Skip unreadable files
        }

        // Try parsing as DefinitionList first
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

        // Fall back to single Triplet parsing
        var t Triplet
        if err := json.Unmarshal(data, &t); err != nil {
            return nil // Skip invalid JSON
        }

        t.Path = path
        kb.triplets = append(kb.triplets, t)
        return nil
    })

    if err != nil {
        return err
    }

    logToFile("KB LOADED | Loaded %d triplet(s) into memory", len(kb.triplets))
    return nil
}

// Reload reloads the knowledge base from disk
func (kb *MemoryKB) Reload() error {
    return kb.Load(kb.kbDir)
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

    var results []Triplet
    normalizedVerb := strings.TrimSuffix(q.Verb, "?")
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

// matchesWithNormalizedVerb checks if a triplet matches the query with normalized verb
func matchesWithNormalizedVerb(q Query, t Triplet, normalizedVerb string) bool {
    // Check temporal context first
    if q.TemporalCtx != "" {
        if !matchesTemporal(t.Date, q.TemporalCtx) {
            return false
        }
    }

    // Use normalized verb for matching (strip '?' from query)
    if normalizedVerb != "" && !strings.Contains(strings.ToLower(t.Verb), strings.ToLower(normalizedVerb)) {
        return false
    }

    // Check object if specified
    if q.Object != "" && !strings.Contains(strings.ToLower(t.Object), strings.ToLower(q.Object)) {
        return false
    }

    // Check context if specified
    if q.Context != "" && !strings.Contains(strings.ToLower(t.Context), strings.ToLower(q.Context)) {
        return false
    }

    return true
}

// matchesTemporal checks if a triplet's date matches the temporal context
func matchesTemporal(date string, temporalCtx string) bool {
    return strings.Contains(date, temporalCtx)
}

     

// Global in-memory knowledge base instance
var globalKB *MemoryKB
