# Knowledge Base (KB) Guide

This directory contains the ontology: JSON files that define `Concept` nodes and their relations. The structure of these files (not special-cased Python code) determines how the system matches input, resolves dependencies, satisfies interfaces, and emits output.

## Directory Layout

```
kb/
├── *.json                  # Top-level concepts (nature, time, data, etc.)
├── recipes/                # Recipe INTERFACE + concrete recipe steps
│   ├── recipe.json         # The Recipe interface definition
│   ├── fried_egg.json      # Example concrete recipe
│   └── ...
├── biology/, chemistry/, physics/, ...   # Domain FACTs
├── programming_languages/
│   ├── go.json             # Go language root
│   ├── go/                 # Go-specific concepts
│   │   ├── constructs/     # Syntactic constructs (if, for, block, ...)
│   │   ├── syntax/         # Keyword-level entries
│   │   ├── operators/      # Operator plan templates (sum, ...)
│   │   └── packages/       # stdlib packages + members
│   └── ...
└── linguistics/            # Interrogatives, answers, language model
```

## Concept JSON Shape

Every loadable file produces one or more objects with this shape:

```json
{
  "id": "unique/id/path",
  "kind": "FACT | SYNTACTIC_CONSTRUCT | BUILTIN | INTERFACE | PLAN_TEMPLATE | CLASS | ...",
  "name": "Human readable name",
  "description": "Optional longer text",
  "parents": ["DEPRECATED - use relations.hasParent instead"],
  "relations": {
    "hasParent": [ {"target": "ParentConceptId"}, ... ],
    "isA": "descriptive or classification string / list (e.g. what the concept 'is')",
    "has": [ "properties or parts expressed as relations" ],
    ...
  },
  "keywords": ["trigger", "word", "list"],
  "relations": {
    "needs": [ ... ],
    "produces": [ ... ],
    "requires": [ ... ],
    "hasInstructions": [ ... ],
    "partOf": [ ... ],
    "hasParts": [ ... ],
    "specializes": [ ... ],
    "importsPackage": [ ... ],
    ...
  },
  "emitters": [
    { "id": "...", "target": "go", "template": "code {{with}} {{bindings}}" }
  ]
}
```

### Key Fields

- **id**: Globally unique within the ontology. Use `/` for hierarchy (e.g. `programming_languages/go/constructs/if`).
- **kind**: Rough classifier. Common values: `FACT`, `SYNTACTIC_CONSTRUCT`, `BUILTIN`, `PLAN_TEMPLATE`, `INTERFACE`, `CLASS`, `PACKAGE`.
- **parents / isA**: Taxonomy. Use for "is a" relationships (`if_statement` parents `["Statement", "ControlFlowStatement"]`).
- **keywords**: Trigger words/phrases for matching from natural language. The loader does not hard-code verbs; new keywords automatically participate in matching.
- **relations**: The heart of the ontology. See vocabulary below.
- **emitters**: Only concepts with emitters can contribute output text/code. The resolver must pull them in via relations.

## Canonical Relation Vocabulary

Use these consistently. The ontology walker and interface satisfier discover requirements from these names.

### Flow / Dependency
| Relation       | Direction                  | Meaning / Example |
|----------------|----------------------------|-------------------|
| `needs`        | subject → requirement      | This node requires a value/binding of the given type or name. |
| `produces`     | producer → type/value      | This node yields a value of the given type (or named result). |
| `producedBy`   | consumer → producer(s)     | Inverse annotation (rare; usually just use `produces` on the source). |

Interrogatives (`what`, `how`, `when`, ...) declare `produces` pointing at answer types. The subject of the question (e.g. `botany/banana`) is matched separately by keywords. Definition text for plain FACTs is synthesized from their `definitions` or `parents` via a narrow fallback in the renderer.

### Structural (part-whole)
| Relation   | Direction             | Meaning |
|------------|-----------------------|---------|
| `partOf`   | child → whole         | This concept is a constituent / member / subdomain of the target. (Most common.) |
| `hasParts` | whole → children      | This container structurally holds the listed children. (Used for Block, Package, etc.) |

**Guideline**: Prefer `partOf` (on the leaf) + `hasParts` (on the container) over vague or overloaded terms like `contains`, `constitutes`, `madeOf`, etc. We intentionally removed `relatedTo` because it was too generic and did not drive useful resolution.

### Implementation / Specialization
| Relation             | Direction               | Meaning |
|----------------------|-------------------------|---------|
| `specializes`        | concrete → abstract     | This is a concrete realization of the abstract concept (e.g. `fmt_println` specializes `PrintOperation`). |
| `implements`         | concrete → interface    | Alias for specializes in some contexts. |
| `isImplementationOf` | (legacy)                | Avoid; use `specializes`. |

### Import / Package
| Relation          | Direction             | Meaning |
|-------------------|-----------------------|---------|
| `importsPackage`  | user → package        | This construct requires the given package to be imported. |
| `belongsToPackage`| member → package      | This symbol lives in the given package. |
| `imports`         | package → imports     | Package declares import statements. |
| `exports`         | package → bindings    | Package makes these bindings visible. |

### Interface Contracts (Recipe-style)
| Relation        | Direction             | Meaning |
|-----------------|-----------------------|---------|
| `hasIngredients`| recipe → ingredients  | List of required inputs (may use `isClass: true` for open sets). |
| `hasInstructions`| recipe → steps        | Ordered list of action step concept ids. |
| `requires`      | interface → spec      | Declares what relations an implementing concept must provide (used by `Recipe`). |

### Other useful
- `hasBody`, `hasCondition`, `hasThenBranch`, `hasElseBranch`, `hasCases`, ... — Go AST structural children.
- `hasParameter`, `hasReturnTypes`, `hasSignature`, ... — callable typing.
- `definesScope`, `bindsKey`, `bindsValue`, `iteratesOver` — data flow / scoping.
- `hasSubtypes` — explicit listing of more specific interrogatives / variants.
- `isA`, `has`, `uses`, `produces`, etc. inside `relations` — use these (instead of the removed `definitions` triplet array) to express classification and properties. `hasParent` is now the canonical home for parent links (moved out of top-level `parents`).

### Relations to Avoid or Deprecate
- `relatedTo` — removed from active use. Too generic; it did not participate meaningfully in resolution. Use `produces`/`needs`/`specializes`/`partOf` instead, or just rely on keywords + parents.
- Do not invent new synonyms for `partOf`/`hasParts` (`constitutes`, `isPartOf`, `componentOf`, `madeOf`, ...). Normalize to the canonical pair.
- Avoid `contains` for new files (we migrated the two prior uses to `hasParts`).

## How to Add a New File

1. **Choose a location**
   - Domain fact (biology, chemistry, ...): `kb/<domain>/<concept>.json`
   - Go language construct: `kb/programming_languages/go/constructs/<name>.json` or `syntax/`, `operators/`, etc.
   - New recipe step or concrete recipe: `kb/recipes/<name>.json`
   - New interrogative/linguistic notion: `kb/linguistics/...`

2. **Pick an id**
   - Must be unique.
   - Hierarchical with `/` is preferred: `programming_languages/go/constructs/for_statement`.
   - The leaf name should be descriptive and match common keywords.

3. **Fill required fields**
   ```json
   {
     "id": "programming_languages/go/constructs/for_statement",
     "kind": "SYNTACTIC_CONSTRUCT",
     "name": "For Statement",
     "parents": ["Statement", "ControlFlowStatement"],
     "keywords": ["for", "loop", "iterate"]
   }
   ```

4. **Add relations that let the ontology do the work**
   - What does this need? → `needs`
   - What does this produce? → `produces`
   - Where does it live? → `partOf`
   - What concrete thing implements an abstract op? → `specializes`
   - For recipes: declare `hasIngredients` and `hasInstructions` (see `recipes/fried_egg.json`).

5. **Add emitters only when it should produce output**
   - Emitters are templates with `{{binding}}` holes.
   - A concept without emitters will never appear in final emitted text unless it pulls in children that do emit.

6. **(Optional) Add to an interface**
   - If this is a concrete recipe, set `parents` or `isA` that includes `recipes/recipe`.
   - The `requires` block on the interface tells the satisfier which relations to look for.

7. **Test it**
   ```bash
   python -m unittest test_augment -v
   python main.py
   # Try a sentence that should now match your new concept
   ```

## Examples

### Simple domain fact (hasParent + isA + partOf)

See `kb/biology/cell.json`, `kb/animal.json` (now using `relations.hasParent`, `relations.isA` instead of top-level parents + definitions array).

### Go plan template (needs + produces + emitter)

See `kb/programming_languages/go/operators/sum.json`.

### Interface + implementation (Recipe)

- `kb/recipes/recipe.json` declares the contract via `requires`.
- `kb/recipes/fried_egg.json` provides `hasIngredients` + `hasInstructions` and `parents: ["recipes/recipe"]`.

### Structural container (hasParts)

See the updated `kb/programming_languages/go/constructs/block.json` and `package.json`.

## Loading & Resolution Notes

- `kb.py:Ontology.load_from_directory` walks `kb/**/*.json`.
- After load, `_resolve_links` turns string ids inside `parents` and `relations` into live `Concept` references where possible.
- `find_concepts_matching` is keyword/id/name driven (strict mode) or broader.
- `_resolve_dependencies` + `resolve_dependencies` walk `needs`/`produces` primarily, then selected structural/implementation relations.
- Interface satisfaction (`apply_interface_satisfaction`) discovers requirements via `requires` on INTERFACE nodes and matches from available pool using `parents` for class membership.
- Only emitter-bearing nodes that the resolver included contribute to `emit()` output.
- Factual nodes (FACT) carry knowledge via `relations` (`hasParent`, `isA`, `has`, `partOf`, ...). They participate in matching and resolution (e.g. class membership via parents) but only emit when they (or nodes they pull in) declare `emitters`. No special `definitions` handling or auto "X is Y" emission exists in the renderer.

## Maintenance Guidelines

- When you add a new relation name that the resolver or interface logic should honor, update the discovery code in `augment.py` and/or `kb.py` (and document it here).
- Run tests after any KB change.
- Prefer data (relations + parents + keywords) over Python special cases.
- Keep relation names stable and minimal. When two names mean the same thing, pick one and migrate.

## Updating this document

Edit `kb/README.md`. If you change core loader or resolver behavior, also sync `AGENTS.md` and `README.md`.
