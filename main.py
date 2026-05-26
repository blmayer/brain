import nltk
from coreference_resolver import resolve_pronouns
from logging_config import setup_logging
from augment import tree_to_solved_plan, emit


def process_input(task):
    # Tokenize and parse the input
    tokens = nltk.word_tokenize(task)
    tagged = nltk.pos_tag(tokens)
    parsed_tree = nltk.chunk.ne_chunk(tagged)
    
    # Resolve pronouns and get the new tree
    resolved_tree = resolve_pronouns(parsed_tree)
    
    return resolved_tree, parsed_tree


if __name__ == "__main__":
    setup_logging()  # Can be overridden with BRAIN_LOG_LEVEL=DEBUG
    from logging_config import get_logger
    logger = get_logger(__name__)
    logger.info("Starting Brain (ontology-driven mode)")

    while True:
        # Accept user input
        task = input("Enter a sentence (or 'exit' to quit): ")
        
        if task == "exit":
            break
        
        # Process the input
        resolved_tree, parsed_tree = process_input(task)
        
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

        # --- New pipeline: from parsed trees → generic plan → KB augmentation → emission ---
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
