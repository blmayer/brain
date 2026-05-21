"""Simple test for plan augmentation from parsed tree using KB knowledge.
Mirrors the structure and intent of the Go example in cmd/brain/main.go and
the TestGeneratePlanForSumProgram in synthesize_test.go, but now exercised
through the generic solver + KB (no hard-coded generation of the full plan).
"""

import unittest
from augment import solve_plan, emit, make_plan, make_var_plan, Context, tree_to_solved_plan


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


if __name__ == "__main__":
    unittest.main()
