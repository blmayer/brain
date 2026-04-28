package parse

import (
	"encoding/json"
	"fmt"
	"strings"
)

// Triplet represents a knowledge statement
type Triplet struct {
	Subject      string  `json:"subject"`
	Verb         string  `json:"verb"`
	Object       string  `json:"object"`
	Confidence    float64 `json:"confidence"`
	Source       string  `json:"source"`
	Date         string  `json:"date"`
	Context      string  `json:"context"`
	TemporalCtx  string  `json:"temporal_context"`
	Path         string  `json:"path"`
}


// Question returns true if the triplet represents a question (verb ends with ?)
func (t Triplet) IsQuestion() bool {
	return strings.HasSuffix(t.Verb, "?")
}

// NormalizedVerb removes the ? suffix for comparison
func (t Triplet) NormalizedVerb() string {
	if strings.HasSuffix(t.Verb, "?") {
		return strings.TrimSuffix(t.Verb, "?")
	}
	return t.Verb
}

func NewTriplet(subject, verb, object string) Triplet {
	return Triplet{
		Subject:    subject,
		Verb:       verb,
		Object:     object,
		Confidence: 1.0,
		Source:     "default",
	}
}

// SystemPrompt returns the system prompt for the query parser
func SystemPrompt() string {
	return `You are a query parser for a knowledge base system.
Your task is to convert natural language into structured triplet queries.

A user might ask questions, make statements, or do both in the same message.
- Questions (asking for info) have verbs ending with '?' like "is?", "eats?", "was?"
- Statements (telling info) have verbs without '?' like "like", "is", "eats"
- Decompose the request into the smallest possible logical steps.
- Use a "chaining" style: if the user wants a program, the first triplet might be "user wants program", the next "program has language", the next "language is golang", etc.
- Ensure the triplets capture all requirements (inputs, outputs, operations, constraints).

Examples:
- "hi" or "hello" -> {"triplets": [{"subject": "user", "verb": "say", "object": "hi"}]}
- "What is a banana?" -> {"triplets": [{"subject": "banana", "verb": "is?"}]}
- "I like pizza" -> {"triplets": [{"subject": "user", "verb": "like", "object": "pizza"}]}
- "write a go program that takes 2 numbers as input and prints their sum" -> {
  "triplets": [
    {"subject": "user", "verb": "wants", "object": "program"},
    {"subject": "program", "verb": "is", "object": "golang"},
    {"subject": "program", "verb": "requires", "object": "2 inputs"},
    {"subject": "program", "verb": "performs", "object": "summation"},
    {"subject": "program", "verb": "outputs", "object": "sum"}
  ]
}

Return ONLY valid JSON with keys: triplets (array of {subject, verb, object}), ambiguous, needs_update (default false).
Don't include code fences or other formatting, your output must start with '{'.
`
}

// QueryResult contains the query parser results
type QueryResult struct {
	Triplets      []Triplet `json:"triplets"`
	Ambiguous     bool      `json:"ambiguous,omitempty"`
	NeedsUpdate   bool      `json:"needs_update,omitempty"`
}

// ParseResult parses the LLM response into a QueryResult
func ParseResult(response string) (*QueryResult, error) {
	cleaned := strings.TrimSpace(response)

	var result QueryResult
	err := json.Unmarshal([]byte(cleaned), &result)
	return &result, err
}

// MergeTriplets merges the new triplets with existing knowledge
// Returns the updated knowledge base and any conflicts
func MergeTriplets(newTriplets []Triplet, existing []Triplet) ([]Triplet, []Triplet, error) {
	// Group new triplets by their verb for conflict detection
	newByVerb := make(map[string][]Triplet)
	for _, t := range newTriplets {
		key := fmt.Sprintf("%s:%s", t.Subject, t.NormalizedVerb())
		newByVerb[key] = append(newByVerb[key], t)
	}

	var merged []Triplet
	var conflicts []Triplet

	// Process each triplet
	for _, t := range newTriplets {
		key := fmt.Sprintf("%s:%s", t.Subject, t.NormalizedVerb())
		if _, exists := newByVerb[key]; !exists && t.Confidence >= 0.5 {
			// First occurrence
			merged = append(merged, t)
		} else {
			// Multiple entries with same structure - potential conflict
			conflicts = append(conflicts, t)
		}
	}

	// Keep only unique triplets
	seen := make(map[string]bool)
	var unique []Triplet
	for _, t := range newTriplets {
		key := fmt.Sprintf("%s|%s|%s", t.Subject, t.Verb, t.Object)
		if !seen[key] {
			seen[key] = true
			unique = append(unique, t)
		}
	}

	return unique, nil, nil
}

// QueryTriplets extracts question triplets from a result for context
func QueryTriplets(result *QueryResult) []Triplet {
	var qs []Triplet
	for _, t := range result.Triplets {
		if t.IsQuestion() {
			qs = append(qs, t)
		}
	}
	return qs
}

