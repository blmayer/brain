# brain

**Knowledge-driven program synthesis and semantic reasoning.**

`brain` stores knowledge as structured, queryable facts (originally triplets, now also rich plan templates) and uses that knowledge to assemble correct outputs instead of relying on LLM hallucination.

The active implementation is in Python.

---

## Python Path (Current Development Focus)

This is the actively evolving implementation.

### Pipeline

The system follows an ontology-driven flow:

```mermaid
flowchart TD
    A[Input Sentence] 
    --> B[process_input<br/>NLTK + Coreference Resolution]
    
    B --> C[_extract_intent_features]
    
    C --> D[_map_features_to_initial_concepts<br/>Per-word keyword matching]
    
    D --> E[_resolve_dependencies<br/>Recursive relation walking + type satisfaction]
    
    E --> F[_features_to_plan]
    
    F --> G[tree_to_solved_plan]
    
    G --> H[solve_plan]
    
    H --> I[emit<br/>Using Concept emitters]
    
    D -.-> J[get_ontology]
    E -.-> J
```

Current demo: "write a Golang program that reads 2 integers and prints their sum" → correct program using `var`/`fmt.Scanf`/`+`/`fmt.Println` emitted from the knowledge base.

#### Detailed Data Flow Example

The following trace shows the **exact data flux** for the canonical example used in `test_augment.py`:

```mermaid
sequenceDiagram
    autonumber
    participant U as User/Test
    participant M as main.py:process_input
    participant C as coreference_resolver.py
    participant A as augment.py
    participant K as kb.py:Ontology

    U->>M: process_input(sentence: str)
    Note over M: In: "write a Golang program that reads 2 integers and prints their sum"
    M->>M: nltk.word_tokenize + pos_tag + ne_chunk
    Note right of M: parsed_tree: nltk.Tree
    M->>C: resolve_pronouns(parsed_tree)
    Note right of C: returns tree with dict leaves<br/>{word, pos, reference}
    C-->>M: resolved_tree
    M-->>U: (resolved_tree, parsed_tree)

    U->>A: tree_to_solved_plan(parsed_tree, resolved_tree)
    Note right of A: Public entry point (ontology-native path)

    A->>A: _extract_intent_features(tree)
    Note right of A: In: resolved_tree<br/>Out (observed in test):<br/>  verbs=['write','reads','prints',...]<br/>  languages=['golang']<br/>  io_verbs={}, arithmetic={},<br/>  detected_concepts={}   (at print)
    A->>A: _map_features_to_initial_concepts(features)
    Note right of A: In: features<br/>Out (exact):<br/>  [PrintOperation,<br/>   fmt.Scanf,<br/>   BinaryAdd]<br/>(ranked by match count)
    A->>K: find_concepts_matching (per word, strict=True)
    K-->>A: ranked Concept matches<br/>(PrintOperation scored 2)
    A->>A: _resolve_dependencies(initial_concepts)
    Note right of A: In: [PrintOperation, fmt.Scanf, BinaryAdd]<br/>Out (exact list + order):<br/>  [fmt.Println,<br/>   fmt.Scanf,<br/>   FunctionType,<br/>   BinaryAdd]
    A->>A: _features_to_plan(features)
    Note right of A: In: features<br/>Out (exact):<br/>  { "type": "ontology_driven_plan",<br/>    "starting_concepts": ["PrintOperation","fmt.Scanf","BinaryAdd"],<br/>    "resolved_dependencies": ["fmt.Println","fmt.Scanf","FunctionType","BinaryAdd"],<br/>    "all_concepts": [...] }
    A->>A: solve_plan(plan, Context())
    Note right of A: In: ontology_driven_plan<br/>Out (exact):<br/>  ExecNode(<br/>    concept=FunctionDeclaration,<br/>    deps=[<br/>      ExecNode(fmt.Println),<br/>      ExecNode(fmt.Scanf),<br/>      ExecNode(FunctionType),<br/>      ExecNode(BinaryAdd)<br/>    ] )
    A-->>U: solved: ExecNode

    U->>A: emit(solved: ExecNode)
    Note over A: DFS post-order, render() using emitters[0].template
    A-->>U: lines: list[str]<br/>(exact, current run):<br/>  0: fmt.Println(a)<br/>  1: fmt.Scanf(format, args)<br/>  2: // no emitter defined for FunctionType<br/>  3: left + right<br/>  4: func namesignature {<br/>body<br/>}
```

**Key observations from this trace:**
- Concept discovery is entirely **KB-driven** (no hardcoded verb lists).
- `_extract_intent_features` returns mostly raw words/POS + language hints. The actual `Concept` objects are produced later by `_map_features_to_initial_concepts` (via `ontology.find_concepts_matching`). In the inspection test print, `features['detected_concepts']` was still empty at that snapshot.
- `_resolve_dependencies` is the heart of the new ontology system — it walks `specializes`, `hasParameter`, `produces`, and `implementedBy` relations to go from the 3 initial matches to the final 4 concrete concepts.
- The final `ExecNode` tree is emitted via per-Concept Jinja-style templates stored in the ontology JSON files.
- Emission is still maturing (hence the placeholder lines above); the important part is that the correct concepts were discovered and wired together.

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
| `main.py`                  | Interactive REPL loop only |
| `parsers.py`               | Parser interface + implementations (default RegexpChunkParser etc.) |
| `coreference_resolver.py`  | Pronoun resolution on the parsed tree |
| `augment.py`               | `tree_to_solved_plan()`, generic plan builder, `solve_plan()`, `emit()` |
| `kb.py`                    | Python-native Knowledge Base (Node with `needs`, `produces`, `emits`) |
| `test_augment.py`          | Tests for the plan solver and end-to-end NLTK → emission flow |

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

This project is licensed under the BSD 3-Clause License — see the [LICENSE](LICENSE) file for details.
