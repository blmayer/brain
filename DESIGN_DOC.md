# Project Design: Semantic Decomposition & Graph-Based Assembly

## Overview
The goal is to move away from pure LLM-based code generation towards a **Knowledge-Driven Assembly** model. Instead of asking an LLM to "write code," we use the LLM to "translate intent" and then use a structured Knowledge Base (`kb/`) to "assemble instructions."

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

### Phase 3: Knowledge-Driven Assembly (The KB Resolver)
For every node in the Implementation Graph, the system performs a targeted query against the `kb/` directory.
- **Process:**
    1.  Identify the node's semantic requirements.
    2.  Query the Knowledge Base (e.g., `kb/programming_languages/go/syntax/var.json`).
    3.  Synthesize a **Code Fragment** using the retrieved facts.
- **Crucial Aspect:** The KB provides the "atoms" of code (the syntax, the operators, the library functions) to ensure correctness and prevent hallucinations.

## Advantages
1.  **Precision:** Uses structured facts instead of probabilistic guesses.
2.  **Traceability:** Every line of code can be traced back to a specific Knowledge Base entry.
3.  **Scalability:** New languages or libraries can be added simply by expanding the `kb/` directory without retraining the LLM.
4.  **Complexity Management:** Large tasks are broken into small, solvable sub-problems.

