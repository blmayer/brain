package parse

import (
	"encoding/json"
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
func SystemPrompt(mode string) string {
	switch mode {
	case "intent_decomposition":
		return `You are an Intent Decomposition Engine. 
Your task is to take a user's request (e.g., a request to write a program or perform a task) and decompose it into a sequence of logical, interconnected triplets that describe the requirements and the structure of the task.

Each triplet must follow the format: {"subject": "...", "verb": "...", "object": "..."}.
The triplets should form a chain or a dependency sequence that describes the "what" and the "how" of the request.

Rules:
1. Decompose the request into the smallest possible logical steps.
2. Use a "chaining" style: if the user wants a program, the first triplet might be "user wants program", the next "program has language", the next "language is golang", etc.
3. Ensure the triplets capture all requirements (inputs, outputs, operations, constraints).
4. Return ONLY a valid JSON object with the key "triplets" containing an array of these triplets.

Example:
Input: "write a go program that takes 2 numbers as input and prints their sum"
Output: {
  "triplets": [
    {"subject": "user", "verb": "wants", "object": "program"},
    {"subject": "program", "verb": "is", "object": "golang"},
    {"subject": "program", "verb": "requires", "object": "2 inputs"},
    {"subject": "program", "verb": "performs", "object": "summation"},
    {"subject": "program", "verb": "outputs", "object": "sum"}
  ]
}

Return ONLY valid JSON.`

	default: // default to knowledge query mode
		return `You are a query parser for a knowledge base system.
Your task is to convert natural language into structured triplet queries.

A user might ask questions, make statements, or do both in the same message.
- Questions (asking for info) have verbs ending with '?' like "is?", "eats?", "was?"
- Statements (telling info) have verbs without '?' like "like", "is", "eats"

Convert each clause into a subject-verb-object triplet.

Examples:
- "hi" or "hello" -> {"triplets": [{"subject": "user", "verb": "say", "object": "hi", "temporal_context": "present"}]}
- "What is a banana?" -> {"triplets": [{"subject": "banana", "verb": "is?", "object": "", "temporal_context": "present"}]}
- "I like pizza" -> {"triplets": [{"subject": "user", "verb": "like", "object": "pizza", "temporal_context": "present"}]}
- "Tell me about the sun" -> {"triplets": [{"subject": "sun", "verb": "is?", "object": "", "temporal_context": "present"}]}

Important:
- Always return an array of triplets, even for single inputs
- Questions have verbs ending with '?' (e.g., "is?", "eats?")
- Statements have verbs without '?' (e.g., "like", "is", "think")

Return ONLY valid JSON with keys: triplets (array of {subject, verb, object, context, temporal_context}), ambiguous, needs_update.
Set ambiguous to true if the query could have multiple meanings.
Set needs_update to true if the question is about new knowledge not in the KB.`
	}
}

// ParseResult parses the LLM response into a QueryResult
func ParseResult(response string) (*QueryResult, error) {
	var result QueryResult
	err := json.Unmarshal([]byte(response), &result)
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


