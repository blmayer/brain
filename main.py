"""Interactive entry point for the Brain program-synthesis system.

The main loop is intentionally minimal:
- It only handles I/O (the REPL) and wires the pluggable parser into the
  KB-driven augmentation / emission pipeline.
- All parsing logic lives in parsers.py behind the Parser interface.
"""

from logging_config import setup_logging
from parsers import get_default_parser
from augment import tree_to_solved_plan, emit


if __name__ == "__main__":
    setup_logging()  # Can be overridden with BRAIN_LOG_LEVEL=DEBUG
    from logging_config import get_logger
    logger = get_logger(__name__)
    logger.info("Starting Brain (ontology-driven mode)")

    parser = get_default_parser()

    while True:
        # Accept user input
        task = input("Enter a sentence (or 'exit' to quit): ")
        
        if task == "exit":
            break
        
        # Process the input via the pluggable Parser interface
        resolved_tree, parsed_tree = parser.parse(task)
        
        # Print the parsed tree
        print("\nParsed Tree:")
        print(parsed_tree)
        
        # Print the resolved tree
        print("\nResolved Tree (with references):")
        print(resolved_tree)
        
        # Print pronoun resolutions in a user-friendly way
        print("\nPronoun Resolutions:")
        found_resolutions = False
        for leaf in resolved_tree.leaves():
            if leaf['reference'] is not None:
                print(f"{leaf['word']} ({leaf['pos']}) -> {leaf['reference']}")
                found_resolutions = True
        
        if not found_resolutions:
            print("No pronouns found to resolve.")

        # --- Pipeline: from parsed trees → generic plan → KB augmentation → emission ---
        print("\n=== KB-Augmented Plan Emission ===")
        try:
            solved = tree_to_solved_plan(parsed_tree, resolved_tree)
            lines = emit(solved)

            if lines:
                for line in lines:
                    print(line)
            else:
                print("(No output lines generated from the current knowledge base)")
        except Exception as e:
            print(f"[Pipeline error] {e}")
