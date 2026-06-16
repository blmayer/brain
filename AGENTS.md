# AGENTS.md

Instructions for AI coding agents working in this repository.

---

## Project Overview

This is a **knowledge-driven program synthesis** project. The goal is to parse natural language, turn it into a structured plan, augment that plan using a knowledge base, and emit correct output (e.g. source code).

The active implementation is the Python path using NLTK for parsing + a custom plan solver + Python KB (`kb.py`).

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
5. Uses the Knowledge Base (`kb.py`) to augment the plan
6. Emits the final result via `emit()`

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

**Important:** `tree_to_solved_plan(parsed_tree, resolved_tree)` is the main generic entry point that bridges raw NLTK output to the KB-driven solver.

---

## Development Guidelines for Agents

- **Prefer the Python path** for new features unless explicitly told otherwise.
- The Knowledge Base lives primarily in `kb.py`. Add new templates (e.g. loops, conditionals, other languages) or FACTs (model "X isA Y" via top-level `isA` + `parents`; use `relations` for needs/produces/partOf/specializes etc.) there.
- Feature detection in `_extract_intent_features()` is **KB-driven** — new node IDs in `KB` are automatically discovered from user sentences.
- When changing the plan emission logic (including structural render fallback for isA/parents on FACTs), update both `augment.py` and `kb.py`.
- Keep `AGENTS.md` and `README.md` in sync when setup steps change.
- Always run the relevant tests after making changes to `augment.py`, `kb.py`, or the JSON files under `kb/`.
- Recipes live at `kb/recipes/`. The JSON files under `kb/programming_languages/go/` (plan templates) + `kb/recipes/` are the data source for executable steps and should follow the current `Concept` shape (relations + parents/isA + emitters).

---

## Common Tasks

**Add a new capability to the KB:**
1. Add a new `Concept` (as JSON) under `kb/`. Use `parents`/`isA` for "is a" (e.g. banana isA fruit), `relations` for other links, `emitters` for renderable output.
2. (Optional) Add corresponding JSONs under `kb/programming_languages/...` or `kb/recipes/` for reference
3. Update tests in `test_augment.py` if behavior changes

**Improve natural language understanding:**
- Modify logic in `_extract_intent_features()` and `_features_to_plan()` in `augment.py`
- Keep detection generic (look at KB keys rather than hardcoding verbs)

---

This file should be read by any AI agent before starting work on this codebase.
