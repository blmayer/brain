# Golang Ontology

This directory contains the structured knowledge representation (ontology) for the Go programming language.

## Structure

- `core/`           → Metamodel and base classes (to be added)
- `golang/`         → Domain-specific concepts for Go
  - `constructs/`   → Syntactic language constructs (statements, declarations, expressions, etc.)
  - `types/`        → Type system concepts
  - `semantics/`    → Semantic concepts (Bindings, Scopes, Effects, etc.)
  - `packages/`     → Package and module level concepts
  - `idioms/`       → Go-specific idioms and best practices

## Current Status

This is an evolving ontology. The goal is to move from flat plan templates (`kb.py`) to a rich, queryable, and reason-able knowledge base.

## Key Design Goals

- Separate **what** a construct is from **how** it is emitted
- Support multiple valid implementations for the same intent
- Enable type-aware and context-aware planning
- Make the knowledge base extensible through data (JSON) rather than code

See `docs/Golang-Ontology-Spec.md` for the full specification.
