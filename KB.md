# Brain Project Knowledge Base

## Overview
Brain is a knowledge base system built in Go that uses LLMs to:
1. Parse natural language questions into structured triplets (S-V-O)
2. Search a knowledge base stored in JSON files
3. Synthesize responses from retrieved triplets
4. Dynamically add new knowledge when queries aren't answered

## Project Structure

```
/
├── cmd/brain/main.go           # Entry point, orchestrates the system
├── internal/
│   ├── config/config.go        # LLM provider configuration
│   ├── config/config_test.go   # Tests for config
│   ├── llm/llm.go              # HTTP client for LLM API calls
│   ├── llm/llm_test.go         # Tests for LLM client
│   ├── parse/parse.go          # Natural language to triplet parser
│   ├── parse/parse_test.go     # Tests for parser
│   ├── search/search.go        # Knowledge base search logic
│   ├── search/search_test.go   # Tests for search
│   ├── synthesize/synthesize.go # Response synthesis
│   └── synthesize/synthesize_test.go # Tests for synthesis
├── kb/                         # Knowledge base (definitions and relationships)
│   ├── banana.json            # banana is fruit, edible, yellow, programming language
│   ├── bracket.json           # [ is array literal (lua), slice literal (go)
│   ├── cat.json               # cat is mammal
│   ├── python.json            # python is programming language
│   └── sun.json               # sun is star
│   └── cat/                   # Relationships for cat
│       ├── has/               # cat has fur/teeth
│       │   ├── fur.json       # cat has fur
│       │   └── teeth.json     # cat has teeth
│       └── eats/              # cat eats meat
│           └── meat.json      # cat eats meat
├── config.json                 # Current LLM configuration
└── main                        # Compiled binary
```

## Data Model
## Data Model

### Triplet Structure
```json
{
  "subject": "string",
  "verb": "string",
  "object": "string",
  "confidence": 0.0-1.0,
  "source": "string",
  "date": "YYYY-MM-DD",
  "path": "string",
  "context": "string (optional)"
}
```

### DefinitionList Structure (for kb/)
```json
{
  "subject": "string",
  "definitions": [
    {
      "subject": "string",
      "verb": "string",
      "object": "string",
      "confidence": 0.0-1.0,
      "source": "string",
      "date": "YYYY-MM-DD",
      "context": "string (optional)"
    }
  ],
  "path": "string"
}
```
```go
type Query struct {
    Subject     string
    Verb        string
    Object      string
    Context     string   // optional context filter
    TemporalCtx string   // temporal context for filtering
}
```

## LLM Configuration

### Providers
- openai (default)
- mistral
- anthropic (TODO)

### Model Configuration (config.json)
```json
{
  "input": {
    "provider": "openai",
    "model": "gpt-4",
    "api_key": "..."
  },
  "output": {
    "provider": "openai",
    "model": "gpt-4",
    "api_key": "..."
  }
}
```

## Search Logic

### Matching Algorithm
1. Check temporal context first (if specified)
2. Check context filter (if specified)
3. Check subject (case-insensitive substring)
4. Check verb (case-insensitive substring)
5. Check object (case-insensitive substring)

- **kb/**: Single directory for all knowledge (definitions and relationships)

Converts retrieved triplets into natural language responses:
- Prioritizes higher confidence information
- Notes uncertainty if confidence < 0.5
- Cites sources when available
- Returns "I don't have information about that" if no triplets found

## Parsing Logic

### Examples
- "What is a banana?" → {"subject": "banana", "verb": "is?", "object": ""}
- "What does a cat eat?" → {"subject": "cat", "verb": "eats?", "object": ""}
- "Is Python a programming language?" → {"subject": "python", "verb": "is?", "object": "programming language"}
- "What was the capital of France?" → {"subject": "france", "verb": "had?", "object": "capital", "temporal_context": "past"}

**Important:** For questions, append '?' to the verb to distinguish from statements.

When a query returns no results:
1. Ask LLM to generate new knowledge triplet
When a query returns no results:
1. Ask LLM to generate new knowledge triplet
2. Add to the `kb/` directory
3. Re-search with updated KB
4. Synthesize response
- All triplets are stored in the `kb/` directory
- Files are named `{subject}.json`
- Multiple definitions per subject are stored in DefinitionList format
- Relationships are stored as nested files: `kb/{subject}/{verb}/{object}.json`
- cat is mammal (confidence: 0.95, general knowledge)

### Python (kb/python.json)
- python is programming language (confidence: 0.95, general knowledge)

### Sun (kb/sun.json)
- sun is star (confidence: 0.95, general knowledge)

### Cat Relationships (kb/cat/)
- cat has fur (confidence: 0.95, general/biology)
- cat has teeth (confidence: 0.95, general/biology)
- cat eats meat (confidence: 0.95, general/biology)


Run with: `./main [root_dir] [config_path]`

Default: `./main`

Interactive mode:
- Type questions to query the KB
- Type "quit" or "exit" to exit
- Add "yes" when prompted to add more information

## File Formats

### kb/ Files (Multiple Definitions)
```json
{
  "subject": "subject_name",
  "definitions": [
    {
      "subject": "subject_name",
      "verb": "is",
      "object": "definition",
      "confidence": 0.95,
      "source": "source_name",
      "date": "2024-01-01",
      "context": "general/botany"
    }
  ]
}
```

### Directory Organization
