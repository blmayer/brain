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
├── defs/                       # Subject definitions (multiple triplets per subject)
│   ├── banana.json            # banana is fruit, edible, yellow, programming language
│   ├── bracket.json           # [ is array literal (lua), slice literal (go)
│   ├── cat.json               # cat is mammal
│   ├── python.json            # python is programming language
│   └── sun.json               # sun is star
├── itens/                      # Relationship items (subject/verb/object hierarchy)
│   └── cat/
│       ├── has/
│       │   ├── fur.json       # cat has fur
│       │   └── teeth.json      # cat has teeth
│       └── eats/
│           └── meat.json       # cat eats meat
├── config.json                 # Current LLM configuration
└── main                        # Compiled binary
```

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

### DefinitionList Structure (for defs/)
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

### Query Structure
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

### Directory Organization
- **defs/**: Flat JSON files, multiple triplets per subject
- **itens/**: Nested hierarchy `subject/verb/object.json`

## Synthesis Logic

### System Prompt
Converts retrieved triplets into natural language responses:
- Prioritizes higher confidence information
- Notes uncertainty if confidence < 0.5
- Cites sources when available
- Returns "I don't have information about that" if no triplets found

## Parsing Logic

### System Prompt
Converts natural language questions into S-V-O triplets.

### Examples
- "What is a banana?" → {"subject": "banana", "verb": "is", "object": ""}
- "What does a cat eat?" → {"subject": "cat", "verb": "eats", "object": ""}
- "Is Python a programming language?" → {"subject": "python", "verb": "is", "object": "programming language"}
- "What was the capital of France?" → {"subject": "france", "verb": "had", "object": "capital", "temporal_context": "past"}

## Dynamic Knowledge Addition

When a query returns no results:
1. Ask LLM to generate new knowledge triplet
2. Add to appropriate directory (defs/ or itens/)
3. Re-search with updated KB
4. Synthesize response

### AddTriplet Logic
- **defs/**: For "is" verbs or empty verbs (subject definitions)
- **itens/**: For relationship verbs (has, eats, uses, etc.)
  - Creates nested directory: `itens/subject/verb/object.json`

## Current Knowledge Base Content

### Banana (defs/banana.json)
- banana is fruit (confidence: 0.95, general/botany)
- banana is edible (confidence: 0.98, general/botany)
- banana is yellow (confidence: 0.90, general/botany)
- banana is programming language (confidence: 0.75, computer-science/programming-languages/banana-lang)

### Bracket (defs/bracket.json)
- [ is array literal (confidence: 0.98, lua documentation)
- [ is slice literal (confidence: 0.95, golang spec)

### Cat (defs/cat.json)
- cat is mammal (confidence: 0.95, general knowledge)

### Python (defs/python.json)
- python is programming language (confidence: 0.95, general knowledge)

### Sun (defs/sun.json)
- sun is star (confidence: 0.95, general knowledge)

### Cat Relationships (itens/cat/)
- cat has fur (confidence: 0.95, general/biology)
- cat has teeth (confidence: 0.95, general/biology)
- cat eats meat (confidence: 0.95, general/biology)

## File Formats

### defs/ Files (Multiple Definitions)
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

### itens/ Files (Single Triplet)
```json
{
  "subject": "subject_name",
  "verb": "has",
  "object": "object_name",
  "confidence": 0.95,
  "source": "general knowledge",
  "date": "2024-01-01",
  "context": "general/biology"
}
```

## Entry Point

Run with: `./main [root_dir] [config_path]`

Default: `./main`

Interactive mode:
- Type questions to query the KB
- Type "quit" or "exit" to exit
- Add "yes" when prompted to add more information

