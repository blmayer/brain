# brain

**Knowledge-driven program synthesis and semantic reasoning.**

`brain` stores knowledge as structured, queryable facts (originally triplets, now also rich plan templates) and uses that knowledge to assemble correct outputs instead of relying on LLM hallucination.

The project has two parallel implementations:

- **Active Python path** (new version): NLTK-based natural language parsing + generic plan construction driven by a Python KB (`kb.py`) + knowledge-driven code emission.
- **Legacy Go path**: The original triplet-based KB stored in `kb/*.json` files with LLM-assisted parsing and search.

---

## Python Path (Current Development Focus)

This is the actively evolving implementation.

### Pipeline

```
Natural Language
      │
      ▼
process_input()          # NLTK tokenization + POS tagging + NE chunking + coreference resolution
      │
      ▼
tree_to_solved_plan()    # Generic feature extraction (KB-driven) → Plan tree
      │
      ▼
solve_plan() + KB        # Augment with needs/produces/emits from knowledge base
      │
      ▼
emit()                   # Depth-first rendering of the final output (e.g. Go source)
```

Current demo: "write a Golang program that reads 2 integers and prints their sum" → correct Go program using `var`/`fmt.Scanf`/`+`/`fmt.Println` emitted from the knowledge base.

### Getting Started (Python)

1. Install dependencies:

   ```bash
   pip install nltk
   ```

2. **Download the required NLTK data** (run once):

   ```python
   import nltk
   nltk.download('punkt')
   nltk.download('punkt_tab')          # newer NLTK versions
   nltk.download('averaged_perceptron_tagger')
   nltk.download('maxent_ne_chunker')
   nltk.download('words')
   ```

   Or from the command line:

   ```bash
   python -c "import nltk; nltk.download(['punkt','punkt_tab','averaged_perceptron_tagger','maxent_ne_chunker','words'])"
   ```

3. Run the demo:

   ```bash
   python main.py
   ```

   Type sentences like:
   - `write a Golang program that reads 2 integers and prints their sum`
   - `write a python program that ...`

4. Run the tests:

   ```bash
   python -m unittest test_augment test_coreference_resolver -v
   ```

### Key Python Files

| File                        | Purpose |
|----------------------------|---------|
| `main.py`                  | Interactive entry point + `process_input()` (NLTK pipeline) |
| `coreference_resolver.py`  | Pronoun resolution on the parsed tree |
| `augment.py`               | `tree_to_solved_plan()`, generic plan builder, `solve_plan()`, `emit()` |
| `kb.py`                    | Python-native Knowledge Base (Node with `needs`, `produces`, `emits`) |
| `test_augment.py`          | Tests for the plan solver and end-to-end NLTK → emission flow |

---

## Legacy Go Implementation

The original system (still present in `cmd/brain/` and `internal/`).

### Running (Go)

```bash
export OPENAI_API_KEY=your_key
go run cmd/brain/main.go
```

### Project Structure (Go)

```
cmd/brain/main.go
internal/
├── parse/      # NL → triplets (LLM-assisted)
├── search/     # Filesystem KB search
├── synthesize/ # Triplets → natural language
└── llm/        # OpenAI / Mistral / etc. clients
kb/             # Original JSON knowledge base (triplets + plan templates)
```

Many of the ideas from the Go version (especially the plan expansion + KB-driven emission in `kb/programming_languages/go/...`) have been ported and generalized into the Python `kb.py` + `augment.py` implementation.

---

## Knowledge Base

Knowledge lives in two forms:

1. **Rich plan templates** (`kb.py` + the JSONs under `kb/programming_languages/go/...`)
   - Used by the Python solver (`sum`, `print`, `read`, `declaration`, etc.).
   - Each node declares `needs`, `produces`, and `emits` (text + references).

2. **Triplet KB** (the original `kb/*.json` files)
   - Classic `subject verb object` facts with confidence, context, date, etc.

Adding new capabilities is usually just adding a new node to `kb.py` (or a JSON file). The Python feature extractor automatically recognizes any new node IDs that appear in user sentences.

---

## Design Goals

- Move from "ask the LLM to write code" to **"parse intent + assemble from verified knowledge atoms"**.
- Make the system **extensible by data**, not by code changes.
- Support traceability: every emitted line can be traced back to a specific KB entry.

See `DESIGN_DOC.md` for the original four-phase architecture.

---

## Limitations & Future Work

- The current Python KB is still small (focused on the "sum two numbers" example).
- NLTK parsing is a cheap local approximation — a real LLM parser (as described in the design doc) would be more robust for complex sentences.
- No persistent storage or multi-turn conversation context yet in the Python path.

Contributions that expand `kb.py` with new reusable templates (loops, conditionals, different languages, etc.) are very welcome.

---

## License

No license specified yet. All code is currently experimental.
