"""Simple test for plan augmentation from parsed tree using KB knowledge.
Mirrors the structure and intent of the Go example in cmd/brain/main.go and
the TestGeneratePlanForSumProgram in synthesize_test.go, but now exercised
through the generic solver + KB (no hard-coded generation of the full plan).
"""

import unittest
from augment import (
    solve_plan, emit, make_plan, make_var_plan, Context, tree_to_solved_plan,
    _extract_intent_features, _map_features_to_initial_concepts, 
    _resolve_dependencies, _features_to_plan
)


class TestAugmentWithKB(unittest.TestCase):
    def build_sum_program_plan(self):
        """Build the same plan tree shape as the Go example (and the hardcoded generator).
        In real use the 'parsed' LLM output would produce the high-level parts and
        the augmentation would fill details, but here we attach the decl/read steps
        explicitly as the Go version did.
        """
        decl_a = make_plan("declaration", needs=[make_plan("a")])
        read_a = make_plan("read", needs=[make_plan("a")])
        a_plan = make_var_plan("a", [decl_a, read_a])

        decl_b = make_plan("declaration", needs=[make_plan("b")])
        read_b = make_plan("read", needs=[make_plan("b")])
        b_plan = make_var_plan("b", [decl_b, read_b])

        sum_plan = make_plan("sum", needs=[a_plan, b_plan])
        print_plan = make_plan("print", needs=[sum_plan])
        return print_plan

    def test_emitted_lines_for_sum_program(self):
        """The core test: after solving/augmenting the parsed plan with KB,
        the DFS emit must produce the correct Go statements in dependency order.
        This exercises using knowledge (emits, needs, produces) from kb.py .
        """
        plan = self.build_sum_program_plan()
        ctx = Context()
        root = solve_plan(plan, ctx)
        lines = emit(root)

        expected = [
            "var a int",
            'fmt.Scanf("%d", &a)',
            "var b int",
            'fmt.Scanf("%d", &b)',
            "result := a + b",
            "fmt.Println(result)",
        ]
        self.assertEqual(lines, expected)

    def test_bindings_contain_key_names(self):
        """Sanity: important logical names are bound to the concrete ones from plan."""
        plan = self.build_sum_program_plan()
        ctx = Context()
        root = solve_plan(plan, ctx)

        self.assertIn("result", root.bindings)
        self.assertEqual(root.bindings.get("result"), "result")
        self.assertIn("var_a", root.bindings)
        self.assertEqual(root.bindings.get("var_a"), "a")

    def test_uses_kb_knowledge(self):
        """The solver must have pulled the real 'sum' node from KB (has the + emit etc)."""
        plan = self.build_sum_program_plan()
        ctx = Context()
        root = solve_plan(plan, ctx)
        # root's first dep should be the sum exec (under print)
        # walk to it
        sum_exec = None
        for d in root.deps:
            if d.node.id == "sum":
                sum_exec = d
                break
        self.assertIsNotNone(sum_exec)
        self.assertTrue(any("+" in (getattr(e, "text", "") if hasattr(e, "text") else str(e)) for e in sum_exec.node.emits))

    def test_tree_to_solved_plan_from_nltk_trees(self):
        """End-to-end test using the real NLTK pipeline.

        process_input(sentence) → (parsed_tree, resolved_tree)
        → tree_to_solved_plan(...)  (the new generic function)
        → emit() must produce the expected Go program.

        The function under test must discover 'read', 'print' and 'sum'
        by looking them up in the KB (no hardcoded verb lists).
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

        solved = tree_to_solved_plan(parsed_tree, resolved_tree)
        lines = emit(solved)

        expected = [
            "var a int",
            'fmt.Scanf("%d", &a)',
            "var b int",
            'fmt.Scanf("%d", &b)',
            "result := a + b",
            "fmt.Println(result)",
        ]
        self.assertEqual(lines, expected)

        # Also sanity-check that the KB-driven detector actually found the nodes
        # (we can reach the internal features via a second call if needed,
        # but for the public API we just trust the final emission)
        self.assertIsNotNone(solved)

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
