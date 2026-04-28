# brain

This project is a knowledge base connected with LLMs, it delivers knowledge
in a human readable way. This is going to be the supreme AI.

Current LLMs are inherently unpredictable, they are, in essence, a probability
distribution. This project changes how knowledge is stored. It uses a graph
database that exposes knowledge in its basic form, the triplet:

subject verb object

This way ANYTHING can be written! This also works in a different way, instead of
having layers in RAM this model will simply search the filesystem.


## How it works

A LLM will convert the user prompt into a query, brain runs the query that
returns the knowledge it has, then a LLM will translate that into natural
language.

For example, user asks "what's a banana?", then the LLM should output a query
like this: "banana is?", so brain will search "banana" in the KB. The output
would be like this:

banana is fruit
banana is edible
banana is tree
...

and so on. Then the LLM will convert that into a human readable response:

Banana is a fruit that can be eaten, it is native to equatorial climate...
It also refers to the banana tree, a plant of the Palmares species...

The knowledge graph is implemented in the filesystem, as a bunch of JSON
files, so searching for them is easy.


## Project Structure

```
brain/
├── cmd/brain/main.go      # Main entry point (interactive CLI)
├── config.json            # LLM providers and model settings
├── kb/                    # Knowledge base (definitions and relationships)
│   ├── banana.json        # Array of definitions with contexts
│   ├── cat.json
│   ├── python.json
│   └── sun.json
│   └── cat/
│       ├── has/
│       │   ├── fur.json
│       │   └── teeth.json
│       └── eats/
│           └── meat.json
└── internal/
    ├── config/            # Configuration loading
    ├── llm/               # LLM client (OpenAI, Mistral)
    ├── parse/             # Query parser (NL → triplet)
    ├── search/            # Filesystem search engine
    └── synthesize/        # Response synthesizer (triplet → NL)
```


## Running

```bash
# Set your API key
export OPENAI_API_KEY=your_key_here

# Run the interactive CLI
go run cmd/brain/main.go
```

The program will prompt for questions. Type 'quit' to exit.


## Configuration

Edit `config.json` to customize providers:

```json
{
  "input": {
    "provider": "openai",
    "model": "gpt-4",
    "api_key": ""
  },
  "output": {
    "provider": "openai",
    "model": "gpt-4",
    "api_key": ""
  }
}
```

Supported providers: `openai`, `mistral`, `anthropic`, `minimax`

### Config File Location

The config file is searched in the following order:
1. Path provided as command-line argument
2. `$XDG_CONFIG_HOME/brain/config.json` (or `~/.config/brain/config.json` if `XDG_CONFIG_HOME` is not set)
3. `./config.json` in the current directory (fallback)


## Adding Knowledge
**Adding Knowledge**
**kb/** - Directory for all knowledge (definitions and relationships):
Each subject has a `kb/{subject}.json` file containing an array of definitions:

```json
{
  "subject": "banana",
  "definitions": [
    {
      "verb": "is",
      "object": "fruit",
      "confidence": 0.95,
      "source": "general knowledge",
      "date": "2024-01-01",
      "context": "general/botany"
    },
    {
      "verb": "is",
      "object": "programming language",
      "confidence": 0.80,
      "source": "community knowledge",
      "date": "2024-01-15",
      "context": "computer-science/programming-languages/banana-lang"
    }
  ]
}
```

## Knowledge Base Structure

**kb/** - Directory for all knowledge (definitions and relationships):
Each subject has a `kb/{subject}.json` file containing an array of definitions:

```json
{
  "subject": "[",
  "definitions": [
    {
      "verb": "is",
      "object": "array literal",
      "confidence": 0.98,
      "source": "lua documentation",
      "date": "2024-01-01",
      "context": "computer-science/programming-languages/lua"
    },
    {
      "verb": "is",
      "object": "slice literal",
      "confidence": 0.95,
      "source": "golang spec",
      "date": "2024-01-01",
      "context": "computer-science/programming-languages/go"
    }
  ]
}
```

**Context hierarchy:** `domain/subdomain/specific` allows precise categorization.

### kb/ - Relations with Context

Nested by subject and verb for efficient searching:

```
kb/
├── cat/
│   ├── has/
│   │   ├── fur.json
│   │   └── teeth.json
│   └── eats/
│       └── meat.json
└── banana/
    └── is/
        ├── fruit.json
        └── edible.json
```

Each relation file includes a `context` field for similar disambiguation.

**Goal:** Allow the system to add new knowledge from queries it can't answer

**Changes:**
**Goal:** Allow the system to add new knowledge from queries it can't answer

**Changes:**
1. **Modify `internal/search/search.go`**
   - Add `AddTriplet()` function to write new triplets to JSON files in `kb/`
2. **Modify `internal/synthesize/synthesize.go`**
   - Add `canAnswer()` method: returns true if confidence is sufficient and triplets exist
   - Return flag to main.go indicating if knowledge was found

3. **Modify `cmd/brain/main.go`**
   - When no triplets found, ask LLM to generate new knowledge
   - Prompt LLM: "Based on this question, what knowledge should be added?"
   - Validate and store new triplet with metadata (confidence, source, timestamp)

**Goal:** Enable multi-turn conversations

**Changes:**
1. **Add `internal/context/` package**
   - Store conversation history
   - Build implicit knowledge from previous answers

2. **Modify `cmd/brain/main.go`**
   - Maintain conversation state
   - Pass context to parse and synthesize steps
   - LLM can reference previous turns

### Phase 4: Confidence & Versioning

**Goal:** Handle conflicting facts and uncertainty
## Proposed Architecture

```
brain/
├── cmd/brain/main.go          # Enhanced with knowledge addition, temporal context, conversation
├── config.json
├── kb/                       # All knowledge stored here (definitions and relations)
├── internal/
│   ├── config/
│   ├── llm/
│   ├── parse/                # Enhanced to extract temporal context
│   ├── search/               # Add AddTriplet(), temporal filtering
│   └── synthesize/           # Add canAnswer(), conflict detection
└── knowledge/                # NEW: store conversation logs (optional)
```

├── defs/                      # Definition triplets
├── itens/                     # Relation triplets (nested by subject)
├── internal/
│   ├── config/
│   └── context/               # NEW: conversation history management
└── knowledge/                 # NEW: store conversation logs (optional)
```

---

## Implementation Priority

1. **High Priority:** Dynamic knowledge addition (most immediate value)
2. **High Priority:** Temporal awareness (addresses your specific concern)
3. **Medium Priority:** Conversation context (nice-to-have for user experience)
4. **Low Priority:** Advanced conflict resolution (can be added later)



## Limitations

How do we encode information that changed? e.g Mike is single; Mike is married.
How do we disambiguate things: '[' means different things in lua and in golang.
