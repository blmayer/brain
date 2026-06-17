# AGENTS.md

Instructions for AI coding agents working in this repository.

---

## Project Overview

This is a **knowledge-driven program synthesis** project. The goal is to parse natural language, match it against the ontology to seed a plan, then let the ontology (its relations, interfaces, `needs`/`produces`/`requires`/`hasInstructions`, `parents`/`isA`, etc.) guide resolution, requirement satisfaction, instruction expansion, and what actually gets emitted.

The active implementation is the Python path using NLTK for parsing + a custom plan solver + Python KB (`kb.py`). There are no special hard-coded query handlers — the structure of the KB itself determines the solution.

---

## Initialization / Setup

### 1. Python Dependencies

```bash
pip install -r requirements.txt
```

`requirements.txt` currently contains:
- `nltk>=3.8`
- `numpy>=1.24`

### 2. Required NLTK Data Downloads

These are **mandatory** for the default parser (RegexpChunkParser) and the full pipeline to work:

```bash
python -c "
import nltk
nltk.download(['punkt', 'punkt_tab', 'averaged_perceptron_tagger', 'maxent_ne_chunker', 'words'])
"
```

Or run interactively:

```python
import nltk
nltk.download('punkt')
nltk.download('punkt_tab')
nltk.download('averaged_perceptron_tagger')
nltk.download('maxent_ne_chunker')
nltk.download('words')
```



---

## Running the Project

### Python (Recommended)

```bash
python main.py
```

This starts an interactive loop that:

1. Accepts natural language input
2. Runs NLTK tokenization + POS tagging + named entity chunking
3. Performs coreference resolution (`coreference_resolver.py`)
4. Calls `tree_to_solved_plan()` from `augment.py` (the key generic function)
5. Matches words to KB Concepts, then lets the ontology guide the rest: `_resolve_dependencies`, interface satisfaction, and `resolve_dependencies` walk relations (`needs`, `produces`, `relatedTo`, `requires`, `hasInstructions`, `isA`/`parents`...) to expand the plan.
6. Only emitter-bearing nodes that the ontology resolution included are emitted via `emit()`.

The ontology (not special query code) determines what instructions, answers, or code fragments appear.

Example good input:
- `write a program that reads 2 integers and prints their sum`

---

## Running Tests

All tests use Python's built-in `unittest`:

```bash
# Run everything
python -m unittest discover -v

# Or run specific test files
python -m unittest test_augment -v
python -m unittest test_coreference_resolver -v
```

Key test files:
- `test_augment.py` — tests the plan solver, `tree_to_solved_plan`, KB-driven emission, and end-to-end NLTK → code generation
- `test_coreference_resolver.py` — tests pronoun resolution on parsed trees

---

## Key Files (Python Path)

| File                        | Responsibility |
|----------------------------|---------------|
| `main.py`                  | Interactive REPL loop only (delegates to parsers.get_default_parser()) |
| `parsers.py`               | Parser ABC + RegexpChunkParser (default), Chart, CoreNLP, Stanza impls |
| `coreference_resolver.py`  | Pronoun resolution logic |
| `augment.py`               | `tree_to_solved_plan()`, `solve_plan()`, `emit()`, plan construction |
| `kb.py`                    | Python-native Knowledge Base (`Concept`, `needs`, `produces`, `emitters`, `parents`/`isA`, `relations`) |
| `requirements.txt`         | Python dependencies |
| `test_augment.py`          | Tests for the augmentation + emission pipeline |

**Important:** `tree_to_solved_plan(parsed_tree, resolved_tree)` is the main generic entry point. It seeds concepts from the parse tree; the ontology then guides solution expansion via its relations and resolution logic in `augment.py`.

---

## Development Guidelines for Agents

- **Prefer the Python path** for new features unless explicitly told otherwise.
- The Knowledge Base lives primarily in `kb.py`. Add new templates or FACTs (use `isA` + `parents` for classification; rich `relations` for `needs`/`produces`/`requires`/`hasInstructions`/etc.). The ontology's structure is what guides planning and solution assembly.
- Feature detection in `_extract_intent_features()` is **KB-driven** — new node IDs in `KB` are automatically discovered from user sentences.
- The core principle: **the ontology guides the solution**. After initial concept matching, resolution walks the KB graph; only what the relations bring in (and that have emitters) participates in output. Avoid special-casing queries or manually pushing nodes.
- When changing resolution, interface satisfaction, or emission logic, update both `augment.py` and `kb.py`.
- Keep `AGENTS.md` and `README.md` in sync when setup steps change.
- Always run the relevant tests after making changes to `augment.py`, `kb.py`, or the JSON files under `kb/`.
- Recipes live at `kb/recipes/`. The JSON files under `kb/programming_languages/go/` (plan templates) + `kb/recipes/` are the data source for executable steps and should follow the current `Concept` shape (relations + parents/isA + emitters).

---

## Common Tasks

**Add a new capability to the KB:**
1. Add a new `Concept` (as JSON) under `kb/`. Use `parents`/`isA` for "is a", `relations` (`needs`, `produces`, `requires`, `hasInstructions`, etc.) so the ontology can guide resolution and expansion when this concept is matched.
2. (Optional) Add corresponding JSONs under `kb/programming_languages/...` or `kb/recipes/` for reference
3. Update tests in `test_augment.py` if behavior changes

**Improve natural language understanding:**
- Modify logic in `_extract_intent_features()` and `_features_to_plan()` in `augment.py`
- Keep detection generic (look at KB keys rather than hardcoding verbs). The ontology (not special case code) should drive what a matched concept pulls into the solution.

---

This file should be read by any AI agent before starting work on this codebase.
