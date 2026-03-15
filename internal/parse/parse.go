package parse

import (
	"encoding/json"
)

// QueryRequest represents the input to the query parser
type QueryRequest struct {
	Prompt string `json:"prompt"`
}

// QueryResult represents the parsed query from the LLM
type QueryResult struct {
	Subject     string `json:"subject"`
	Verb        string `json:"verb"`
	Object      string `json:"object"`
	Ambiguous   bool   `json:"ambiguous"`
	Context     string `json:"context,omitempty"`
	TemporalCtx string `json:"temporal_context,omitempty"`
	NeedsUpdate bool   `json:"needs_update"`
}

// SystemPrompt returns the system prompt for the query parser
func SystemPrompt() string {
	return `You are a query parser for a knowledge base system.
Your task is to convert natural language questions into structured triplet queries.

Convert the user's question into a subject-verb-object pattern.

Examples:
- "What is a banana?" -> {"subject": "banana", "verb": "is", "object": "", "temporal_context": "present"}
- "What does a cat eat?" -> {"subject": "cat", "verb": "eats", "object": "", "temporal_context": "present"}
- "Is Python a programming language?" -> {"subject": "python", "verb": "is", "object": "programming language", "temporal_context": "present"}
- "Tell me about the sun" -> {"subject": "sun", "verb": "", "object": "", "temporal_context": "present"}
- "What was the capital of France?" -> {"subject": "france", "verb": "had", "object": "capital", "temporal_context": "past"}
- "In 1990, what was Mike's status?" -> {"subject": "mike", "verb": "was", "object": "single", "temporal_context": "1990"}

Return ONLY valid JSON with keys: subject, verb, object, ambiguous, context, temporal_context.
Set ambiguous to true if the query could have multiple meanings.
Context can help disambiguate (e.g., "programming" for "[ bracket").
Set needs_update to true if the question is about new knowledge not in the KB.`
}

// ParseResult parses the LLM response into a QueryResult
func ParseResult(response string) (*QueryResult, error) {
	var result QueryResult
	err := json.Unmarshal([]byte(response), &result)
	return &result, err
}

