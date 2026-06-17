# Project Design: Semantic Decomposition & Graph-Based Assembly

## Overview
The goal is to move away from pure LLM-based code generation towards a **Knowledge-Driven Assembly** model in which the ontology itself guides the solution.

Instead of asking an LLM to "write code," we use the LLM (or a parser) only to translate intent into initial concepts. The structured Knowledge Base (`kb/`) — through its relations (`needs`, `produces`, `requires`, `hasInstructions`, `parents`/`isA`, etc.), interfaces, and resolution logic — then drives plan expansion, requirement satisfaction, and what executable content actually participates in the final result. Emission is limited to nodes the ontology resolution selected that declare emitters.

## The Four-Phase Pipeline

### Phase 1: Intent Translation (The LLM Parser)
The LLM serves as a semantic translator. It converts unstructured natural language into a structured **Intent Specification**.
- **Input:** Natural Language (e.g., "Write a Go program to sum two numbers")
- **Output:** A list of high-level semantic requirements (e.g., `target: golang`, `action: input_acquisition`, `action: arithmetic_sum`, `action: output_display`).

### Phase 2: Graph Expansion (The Decomposer)
An engine expands the Intent Specification into a **Dependency Graph of Implementation Steps**. This breaks down abstract actions into concrete, granular instructions.
- **Example Expansion:**
    - `input_acquisition` $\rightarrow$ `[declare_variable, scan_input]`
    - `arithmetic_sum` $\rightarrow$ `[perform_addition]`
    - `output_display` $\rightarrow$ `[print_result]`

### Phase 3: Ontology-Guided Assembly (The KB Resolver)
After initial concepts are seeded from the input, the ontology itself guides the solution:
- The resolver walks the KB graph using declared relations (`needs`/`produces`, `relatedTo`, `requires`, `hasInstructions`, `parents`/`isA`, interface contracts, etc.).
- `resolve_dependencies`, interface satisfaction, and requirement expansion pull in only the nodes the ontology says are required.
- The resulting plan contains exactly the executable content (steps, constructs, emitters) dictated by the KB structure.
- **Crucial Aspect:** There are no special query handlers or manually pushed nodes. The shape of the ontology determines what a "how", a recipe, a program synthesis request, etc. will produce. The KB supplies both the atoms *and* the rules for assembling them.

## Advantages
1.  **Precision:** Uses structured facts instead of probabilistic guesses.
2.  **Traceability:** Every line of code can be traced back to a specific Knowledge Base entry.
3.  **Scalability:** New languages or libraries can be added simply by expanding the `kb/` directory without retraining the LLM.
4.  **Complexity Management:** Large tasks are broken into small, solvable sub-problems.

