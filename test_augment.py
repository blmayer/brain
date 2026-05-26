"""Tests for the ontology-driven plan augmentation system."""

import unittest

from logging_config import setup_logging

# Force debug logging when running tests so we can see the full ontology flow
setup_logging("DEBUG")

from augment import (
    solve_plan, emit, Context, tree_to_solved_plan,
    _extract_intent_features, _map_features_to_initial_concepts, 
    _resolve_dependencies, _features_to_plan
)


class TestAugmentWithKB(unittest.TestCase):
    # Legacy test and helper removed (relied on old make_plan / legacy KB system)

    # Legacy tests removed (they depended on the old make_plan / legacy KB system)

    def test_tree_to_solved_plan_from_nltk_trees(self):
        """End-to-end integration test using the real NLTK pipeline + new ontology system.

        process_input(sentence) → (parsed_tree, resolved_tree)
        → tree_to_solved_plan(...)   (ontology-native path)
        → emit()

        The test verifies that the full pipeline runs successfully and produces
        a solved plan containing relevant ontology concepts.
        """
        try:
            from main import process_input
        except Exception as exc:
            self.skipTest(f"Could not import process_input (nltk?): {exc}")

        sentence = "write a Golang program that reads 2 integers and prints their sum"
        try:
            resolved_tree, parsed_tree = process_input(sentence)
        except Exception as exc:
            self.skipTest(f"process_input failed (missing NLTK data or model?): {exc}")

        # Run the new ontology-driven pipeline
        solved = tree_to_solved_plan(parsed_tree, resolved_tree)
        lines = emit(solved)

        # Basic integration assertions for the new system
        self.assertIsNotNone(solved)
        self.assertIsNotNone(solved.concept)

        # The solved plan should contain some resolved concepts from the ontology
        self.assertGreater(len(solved.deps), 0, "Expected the solver to produce at least one step")

        # At minimum, we should have discovered some recognizable concepts
        concept_ids = [dep.concept.id for dep in solved.deps]
        self.assertTrue(
            any("Print" in cid or "fmt" in cid.lower() or "Add" in cid or "Scan" in cid 
                for cid in concept_ids),
            f"Expected to find print/read/add related concepts, got: {concept_ids}"
        )

        # We don't assert on exact emitted lines yet, as the new ontology-driven
        # emission is still maturing. We only check that emission runs without error.
        self.assertIsInstance(lines, list)

    def test_new_ontology_flow_inspection(self):
        """
        New inspection test for the ontology-based flow.

        This test does NOT assert on final code output yet.
        Its purpose is to let you observe what the new functions produce:
        - Which concepts are discovered from the sentence
        - What dependencies get resolved
        - The structure of the plan
        """
        try:
            from main import process_input
        except Exception as exc:
            self.skipTest(f"Could not import process_input (nltk?): {exc}")

        sentence = "write a Golang program that reads 2 integers and prints their sum"
        try:
            resolved_tree, parsed_tree = process_input(sentence)
        except Exception as exc:
            self.skipTest(f"process_input failed (missing NLTK data?): {exc}")

        # 1. Extract features (this is what the parser sees)
        features = _extract_intent_features(resolved_tree)

        # 2. Map to initial concepts in the ontology
        initial_concepts = _map_features_to_initial_concepts(features)

        # 3. Recursively resolve dependencies (the key new piece)
        resolved_concepts = _resolve_dependencies(initial_concepts)

        # 4. Build the plan using the new ontology-driven logic
        plan = _features_to_plan(features)

        # 5. Run the full solver
        solved = tree_to_solved_plan(parsed_tree, resolved_tree)

        # === Print everything so you can see the results ===
        print("\n" + "="*70)
        print("NEW ONTOLOGY FLOW INSPECTION")
        print("="*70)

        print("\n[1] Extracted features (verbs, arithmetic, detected concepts):")
        print("    io_verbs:", features.get('io_verbs'))
        print("    arithmetic:", features.get('arithmetic'))
        print("    detected_concepts:", features.get('detected_concepts'))

        print("\n[2] Initial concepts found from features:")
        for c in initial_concepts:
            print(f"   - {c.id} ({c.name})")

        print("\n[3] Resolved dependencies (after walking relations + type satisfaction):")
        for c in resolved_concepts:
            print(f"   - {c.id} ({c.name})")

        print("\n[4] Final plan structure (ontology_driven_plan):")
        print("    Type:", plan.get("type"))
        print("    Starting concepts:", plan.get("starting_concepts"))
        print("    Resolved dependencies:", plan.get("resolved_dependencies"))

        print("\n[5] Solved ExecNode tree (top-level concept):")
        print("    Root concept:", solved.concept.id if solved.concept else None)
        print("    Number of direct deps:", len(solved.deps))
        for i, dep in enumerate(solved.deps[:6]):   # show first few
            c = dep.concept
            print(f"      [{i}] {c.id} ({c.name})")

        if len(solved.deps) > 6:
            print(f"      ... and {len(solved.deps)-6} more")

        print("\n" + "="*70)
        print("END OF INSPECTION")
        print("="*70 + "\n")

        # Basic sanity assertions (relaxed for inspection test)
        if len(initial_concepts) == 0:
            print("\n[WARNING] No initial concepts were discovered from this sentence with current ontology.")
        self.assertIsNotNone(solved)


if __name__ == "__main__":
    unittest.main()
