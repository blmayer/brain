"""Interactive entry point for the Brain program-synthesis system.

Pipeline: parse → augment → solve → emit (see augment.py).
"""

from logging_config import setup_logging
from augment import parse, augment, solve, emit


if __name__ == "__main__":
    setup_logging()
    from logging_config import get_logger
    logger = get_logger(__name__)
    logger.info("Starting Brain (ontology-driven mode)")

    from kb import get_ontology
    get_ontology()

    while True:
        task = input("Enter a sentence (or 'exit' to quit): ")
        if task == "exit":
            break

        try:
            tree = parse(task)
            print("\nParsed Tree:")
            print(tree)

            augment(tree)
            print("\nAugmented Tree (concepts attached):")
            print(tree)

            solved = solve(tree)
            print("\n=== Emission ===")
            lines = emit(solved)
            if lines:
                for line in lines:
                    print(line)
            else:
                print("(No output lines generated from the current knowledge base)")
        except Exception as e:
            print(f"[Pipeline error] {e}")
