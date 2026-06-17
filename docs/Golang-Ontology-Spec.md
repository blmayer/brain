# Golang Knowledge Ontology Specification

**Version:** 0.2  
**Date:** April 2026  
**Status:** In Progress  
**Focus:** Knowledge-driven program synthesis for Go

---

## 1. Goals

- Move from flat plan templates to a rich, structured, and reason-able ontology.
- Separate **what** a construct is (taxonomy + relations) from **how** it is rendered (emission).
- Support multiple valid ways to achieve the same programming intent.
- Enable type-aware, context-aware, and idiom-aware code generation.
- Make the knowledge base primarily data-driven (JSON + Python loader).

---

## 2. Design Principles

- **Separation of Concerns**: Syntax, Semantics, Types, and Emission are modeled distinctly.
- **Multi-level Modeling**: Syntactic, Semantic, Type, and Pragmatic layers.
- **Reusability**: Use inheritance and relations instead of duplication.
- **Multiple Emitters**: A single concept can have several valid renderings.
- **Gradual Evolution**: Must coexist with and eventually replace the current `Node`-based system in `kb.py`.

---

## 3. Ontology Architecture

The ontology is organized into four layers:

| Layer                | Purpose                              | Examples                              |
|----------------------|--------------------------------------|---------------------------------------|
| Meta Layer           | Language for describing concepts     | `Construct`, `Relation`, `Emitter`    |
| Syntactic Layer      | Language constructs                  | `VarDeclaration`, `IfStatement`       |
| Semantic Layer       | Meaning and effects                  | `Binding`, `Scope`, `FunctionValue`   |
| Pragmatic Layer      | Idioms and best practices            | `ErrorHandlingIdiom`, `ContextPattern`|

---

## 4. Core Metamodel

### Base Class (Conceptual)

```python
class GolangConcept:
    id: str
    kind: ConceptKind
    name: str
    parents: list[str]
    relations: dict[str, list]
    constraints: list
    semantics: SemanticSpec | None
    emitters: list[Emitter]
```

**ConceptKind** values:
- `SYNTACTIC_CONSTRUCT`
- `SEMANTIC_CONCEPT`
- `TYPE`
- `PACKAGE`
- `BUILTIN`
- `IDIOM`

---

## 5. Golang Domain Taxonomy

### 5.1 Core Hierarchy

```
GolangConcept
├── Construct
│   ├── Statement
│   │   ├── DeclarationStatement
│   │   ├── ControlFlowStatement
│   │   └── Block
│   ├── Expression
│   └── Declaration
├── Callable
│   ├── FunctionDeclaration
│   │   └── MethodDeclaration
│   └── FunctionLiteral
├── Type
│   └── FunctionType
└── SemanticEntity
    ├── Binding
    ├── Scope
    └── FunctionValue
```

### 5.2 Functions (Detailed)

See previous modeling decisions:
- `Callable` is the common abstract parent for `FunctionDeclaration` and `FunctionLiteral`.
- `Block` is modeled as a first-class concept (introduces `Scope`).
- Named returns are modeled as `Binding`s (visible in the function body).
- Positional returns are modeled as `ReturnValue`.

### 5.3 Control Flow Statements

```
ControlFlowStatement
├── IfStatement
├── ForStatement
│   └── RangeStatement
├── SwitchStatement
│   ├── ExpressionSwitchStatement
│   └── TypeSwitchStatement
├── SelectStatement
└── JumpStatement (break, continue, goto, fallthrough)
```

**Key Relations**:
- `hasCondition`
- `hasBody` → `Block`
- `hasInit` / `hasPost` (for `For` and `If` with init)
- `bindsKey` / `bindsValue` (for range)
- `hasCases` (for switch/select)

### 5.4 Packages and Imports

- `Package`: Represents a Go package. Has `exports`, `imports`, and `contains`.
- `Import`: Declaration that brings a package into scope.
- Important relation: `dependsOnPackage` (used by the planner to determine required imports).

---

## 6. Relations

Core relations used across the ontology:

- `requires`
- `produces`
- `hasChild` / `contains`
- `hasParameter`, `hasReceiver`, `hasBody`
- `hasNamedReturn`, `hasPositionalReturn`
- `importsPackage`, `belongsToPackage`
- `hasType`
- `canBeImplementedBy`
- `isA` (subtyping)

---

## 7. Emission Model

`Emitter` is a first-class citizen:

```python
class Emitter:
    id: str
    target: str          # "go", "go-idiomatic"
    style: str
    template: str | Callable
    priority: int
    context_requirements: list[str]
```

A concept can have multiple emitters (different styles, different constraints).

---

## 8. Instances and Examples

See accompanying files under:
- `kb/programming_languages/go/constructs/`
- `kb/recipes/`
- `kb/programming_languages/examples/`

---

## 9. Integration with Existing Codebase

- The current `kb.py` will evolve to become the main `Ontology` container.
- `augment.py` / `tree_to_solved_plan` seeds initial concepts from the parse tree; the rest of the solution (dependency expansion, interface satisfaction, instruction ordering, what gets emitted) is guided by the ontology's relations, `parents`/`isA`, `requires`, `hasInstructions`, etc. There is no special-case query handling — the KB structure drives the result.
- JSON files under `kb/` (programming_languages/go/ + recipes/ etc.) are the canonical source of truth for concepts.

---

## 10. Implementation Roadmap

| Phase | Focus                              | Status     |
|-------|------------------------------------|------------|
| 0     | Metamodel + Core JSON Schema       | In Progress|
| 1     | Functions + Basic Control Flow     | In Progress|
| 2     | Packages, Imports, Error Handling  | Next       |
| 3     | Python loader in `kb.py`           | Starting   |
| 4     | Planner integration                | Planned    |
| 5     | Instance examples + "sum program"  | In Progress|

---

*This document is a living specification and will be updated as the ontology evolves.*
