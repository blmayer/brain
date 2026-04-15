package parse

import (
	"encoding/json"
	"fmt"
	"strings"
)
)

// QueryRequest represents the input to the query parser
type QueryRequest struct {
	Prompt string `json:"prompt"`
}

// Triplet represents a single parsed triplet (subject-verb-object)
type Triplet struct {
	Subject     string `json:"subject"`
	Verb        string `json:"verb"`
	Object      string `json:"object"`
	Context     string `json:"context,omitempty"`
	TemporalCtx string `json:"temporal_context,omitempty"`
}

// QueryResult represents the parsed query from the LLM
type QueryResult struct {
	Triplets    []Triplet `json:"triplets"`
	Ambiguous   bool      `json:"ambiguous"`
	NeedsUpdate bool      `json:"needs_update"`
}

// SystemPrompt returns the system prompt for the query parser
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
- "hi" or "hello" -> {"triplets": [{"subject": "user", "verb": "say", "object": "hi", "temporal_context": "present"}]}
- "What is a banana?" -> {"triplets": [{"subject": "banana", "verb": "is?", "object": "", "temporal_context": "present"}]}
- "I like pizza" -> {"triplets": [{"subject": "user", "verb": "like", "object": "pizza", "temporal_context": "present"}]}
- "Tell me about the sun" -> {"triplets": [{"subject": "sun", "verb": "is?", "object": "", "temporal_context": "present"}]}
- "write a go program that takes 2 numbers as input and prints their sum" -> {
  "triplets": [
    {"subject": "user", "verb": "wants", "object": "program"},
    {"subject": "program", "verb": "is", "object": "golang"},
    {"subject": "program", "verb": "requires", "object": "2 inputs"},
    {"subject": "program", "verb": "performs", "object": "summation"},
    {"subject": "program", "verb": "outputs", "object": "sum"}
  ]
}

Return ONLY valid JSON with keys: triplets (array of {subject, verb, object, context, temporal_context}), ambiguous, needs_update.
Set ambiguous to true if the query could have multiple meanings.
Don't include code fences or other formatting like backticks, your output must start with '{'.`
}

// ParseResult parses the LLM response into a QueryResult
// ParseResult parses the LLM response into a QueryResult
func ParseResult(response string) (*QueryResult, error) {
	cleaned := strings.TrimSpace(response)
	if strings.HasPrefix(cleaned, "```json") {
		cleaned = strings.TrimPrefix(cleaned, "```json")
		cleaned = strings.TrimSuffix(cleaned, "```")
	} else if strings.HasPrefix(cleaned, "```") {
		cleaned = strings.TrimPrefix(cleaned, "```")
		cleaned = strings.TrimSuffix(cleaned, "```")
	}
	cleaned = strings.TrimSpace(cleaned)

	var result QueryResult
	err := json.Unmarshal([]byte(cleaned), &result)
	return &result, err
}

// IsQuestion returns true if the verb ends with '?'
func (t Triplet) IsQuestion() bool {
	return len(t.Verb) > 0 && t.Verb[len(t.Verb)-1] == '?'
}

// NormalizedVerb returns the verb without the trailing '?'
func (t Triplet) NormalizedVerb() string {
	if t.IsQuestion() {
		return t.Verb[:len(t.Verb)-1]
	}
	return t.Verb
}


