
package search

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func TestSearch(t *testing.T) {
	// Create a temp knowledge base
	tmpDir := t.TempDir()

	// Create some test files
	testFiles := map[string]string{
		"banana.json":     `{"subject": "banana", "verb": "is", "object": "fruit", "confidence": 0.95, "source": "test", "date": "2024-01-01"}`,
		"cat.json":        `{"subject": "cat", "verb": "is", "object": "mammal", "confidence": 0.95, "source": "test", "date": "2024-01-01"}`,
		"python.json":     `{"subject": "python", "verb": "is", "object": "programming language", "confidence": 0.95, "source": "test", "date": "2024-01-01"}`,
	}

	for filename, content := range testFiles {
		path := filepath.Join(tmpDir, filename)
		if err := os.WriteFile(path, []byte(content), 0644); err != nil {
			t.Fatalf("failed to write test file: %v", err)
		}
	}

	tests := []struct {
		name     string
		query    Query
		wantLen  int
		check    func([]Triplet)
	}{
		{
			name:    "search by subject",
			query:   Query{Subject: "banana"},
			wantLen: 1,
			check: func(results []Triplet) {
				if results[0].Subject != "banana" {
					t.Errorf("Subject = %v, want banana", results[0].Subject)
				}
			},
		},
		{
			name:    "search by verb",
			query:   Query{Verb: "is"},
			wantLen: 3,
		},
		{
			name:    "search by object",
			query:   Query{Object: "fruit"},
			wantLen: 1,
			check: func(results []Triplet) {
				if results[0].Object != "fruit" {
					t.Errorf("Object = %v, want fruit", results[0].Object)
				}
			},
		},
		{
			name:    "search by subject and verb",
			query:   Query{Subject: "cat", Verb: "is"},
			wantLen: 1,
		},
		{
			name:    "search no match",
			query:   Query{Subject: "dog"},
			wantLen: 0,
		},
		{
			name:    "search empty query",
			query:   Query{},
			wantLen: 3,
		},
		{
			name:    "case insensitive",
			query:   Query{Subject: "BANANA"},
			wantLen: 1,
		},
		{
			name:    "partial match",
			query:   Query{Subject: "ban"},
			wantLen: 1,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			results, err := Search(tmpDir, tt.query)
			if err != nil {
				t.Errorf("Search() error = %v", err)
				return
			}
			if len(results) != tt.wantLen {
				t.Errorf("Search() got %d results, want %d", len(results), tt.wantLen)
			}
			if tt.check != nil && len(results) > 0 {
				tt.check(results)
			}
		})
	}
}

func TestSearchInvalidFiles(t *testing.T) {
	tmpDir := t.TempDir()

	// Create invalid JSON file
	os.WriteFile(filepath.Join(tmpDir, "invalid.json"), []byte("not json"), 0644)

	// Create non-json file
	os.WriteFile(filepath.Join(tmpDir, "readme.txt"), []byte("hello"), 0644)

	results, err := Search(tmpDir, Query{})
	if err != nil {
		t.Errorf("Search() error = %v", err)
	}
	// Should return empty, not crash on invalid files
	if len(results) != 0 {
		t.Errorf("Search() got %d results, want 0", len(results))
	}
}

func TestKnowledgeBase(t *testing.T) {
	// Create temp dirs
	tmpDir := t.TempDir()
	defsDir := filepath.Join(tmpDir, "defs")
	itensDir := filepath.Join(tmpDir, "itens")

	os.MkdirAll(defsDir, 0755)
	os.MkdirAll(itensDir, 0755)

	// Create test files in defs
	os.WriteFile(filepath.Join(defsDir, "banana.json"),
		[]byte(`{"subject": "banana", "verb": "is", "object": "fruit", "confidence": 0.95, "source": "test", "date": "2024-01-01"}`), 0644)

	// Create test files in itens (nested)
	os.MkdirAll(filepath.Join(itensDir, "cat", "has"), 0755)
	os.WriteFile(filepath.Join(itensDir, "cat", "has", "fur.json"),
		[]byte(`{"subject": "cat", "verb": "has", "object": "fur", "confidence": 0.95, "source": "test", "date": "2024-01-01"}`), 0644)

	results, err := KnowledgeBase(defsDir, itensDir, Query{Subject: "cat"})
	if err != nil {
		t.Errorf("KnowledgeBase() error = %v", err)
	}

	if len(results) != 1 {
		t.Errorf("KnowledgeBase() got %d results, want 1", len(results))
	}

	results, err = KnowledgeBase(defsDir, itensDir, Query{Subject: "banana"})
	if err != nil {
		t.Errorf("KnowledgeBase() error = %v", err)
	}

	if len(results) != 1 {
		t.Errorf("KnowledgeBase() got %d results, want 1", len(results))
	}

	// Search both
	results, err = KnowledgeBase(defsDir, itensDir, Query{})
	if err != nil {
		t.Errorf("KnowledgeBase() error = %v", err)
	}

	if len(results) != 2 {
		t.Errorf("KnowledgeBase() got %d results, want 2", len(results))
	}
}

func TestTripletPath(t *testing.T) {
	tmpDir := t.TempDir()

	os.WriteFile(filepath.Join(tmpDir, "test.json"),
		[]byte(`{"subject": "test", "verb": "is", "object": "ok", "confidence": 0.95, "source": "test", "date": "2024-01-01"}`), 0644)

	results, _ := Search(tmpDir, Query{Subject: "test"})
	if len(results) > 0 && results[0].Path == "" {
		t.Error("Path should be set in results")
	}
}


func TestAddTripletWithQuestionMark(t *testing.T) {
	// Create temp dirs
	tmpDir := t.TempDir()
	defsDir := filepath.Join(tmpDir, "defs")
	itensDir := filepath.Join(tmpDir, "itens")

	os.MkdirAll(defsDir, 0755)
	os.MkdirAll(itensDir, 0755)

	// Add a triplet with verb "is?" (question style from parser)
	triplet := Triplet{
		Subject:    "banana",
		Verb:       "is?",
		Object:     "yellow fruit",
		Confidence: 0.95,
		Source:     "test",
		Date:       "2024-01-01",
	}

	if err := AddTriplet(triplet, defsDir, itensDir); err != nil {
		t.Fatalf("AddTriplet() error = %v", err)
	}

	// Verify it was stored in defs/ (not itens/)
	expectedPath := filepath.Join(defsDir, "banana.json")
	if _, err := os.Stat(expectedPath); os.IsNotExist(err) {
		t.Errorf("Expected file at %s, but it doesn't exist", expectedPath)
	}

	// Verify the stored verb is normalized (without '?')
	data, _ := os.ReadFile(expectedPath)
	var storedTriplet Triplet
	if err := json.Unmarshal(data, &storedTriplet); err != nil {
		t.Fatalf("Failed to parse stored JSON: %v", err)
	}

	if storedTriplet.Verb != "is" {
		t.Errorf("Stored verb = %q, want %q", storedTriplet.Verb, "is")
	}

	// Now search for it - should find it with verb "is?" query
	results, err := Search(defsDir, Query{Subject: "banana", Verb: "is?"})
	if err != nil {
		t.Fatalf("Search() error = %v", err)
	}
	if len(results) != 1 {
		t.Errorf("Search() got %d results, want 1", len(results))
	}

}
