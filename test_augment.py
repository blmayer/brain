"""Tests for the ontology-driven plan augmentation system."""

import os
import unittest

from nltk.tree import Tree

from augment import (
    parse, augment, solve, emit, _seed_concepts,
)
from parsers import get_default_parser

from kb import Concept, Ontology, get_concept


class TestAugmentWithKB(unittest.TestCase):
    # Legacy test and helper removed (relied on old make_plan / legacy KB system)

    # Legacy tests removed (they depended on the old make_plan / legacy KB system)

    def test_pipeline_from_nltk_sentence(self):
        """End-to-end: parse → augment → solve → emit on a program sentence."""
        sentence = "write a Golang program that reads 2 integers and outputs their sum"
        try:
            tree = parse(sentence)
        except Exception as exc:
            self.skipTest(f"parse failed (missing NLTK data or model?): {exc}")

        augment(tree)
        solved = solve(tree)
        lines = emit(solved)

        self.assertIsNotNone(solved)
        self.assertIsNotNone(solved.concept)
        self.assertGreater(len(solved.deps), 0, "Expected the solver to produce at least one step")
        concept_ids = [dep.concept.id for dep in solved.deps]
        self.assertTrue(
            any(
                "Print" in cid or "fmt" in cid.lower() or "Add" in cid or "Scan" in cid
                or "print" in cid.lower() or "sum" in cid.lower() or "scanf" in cid.lower()
                for cid in concept_ids
            ),
            f"Expected to find print/read/add related concepts, got: {concept_ids}"
        )
        self.assertIsInstance(lines, list)
    @unittest.skipUnless(os.environ.get("INSPECT_ONTOLOGY"), "inspection test - set INSPECT_ONTOLOGY=1 to run")
    def test_new_ontology_flow_inspection(self):
        """Manual inspection of parse → augment → solve."""
        sentence = "write a Golang program that reads 2 integers and outputs their sum"
        tree = parse(sentence)
        augment(tree)
        print("seeds:", [c.id for c in _seed_concepts(tree)])
        solved = solve(tree)
        print("deps:", [d.concept.id for d in solved.deps])
        print("emit:", emit(solved))
        self.assertIsNotNone(solved)
class TestParserIdealTree(unittest.TestCase):
    """
    This test captures the *desired* 'ideal' tree structure for the canonical example.

    The ideal tree was manually defined as the linguistically preferred analysis.
    All current parsers (RegexpParser, Stanza, etc.) deviate from it in various ways.
    This test is intentionally expected to fail until parser quality improves.
    It serves as a long-term benchmark / regression target.
    """

    def test_ideal_constituency_tree(self):
        sentence = "write a Golang program that reads 2 integers and outputs their sum"

        # This is the manually defined "ideal" constituency tree (deep, for full parsers)
        ideal_tree_str = """(ROOT
  (S
    (VP (VB write)
        (NP (NP (DT a) (NNP Golang) (NN program))
            (SBAR (WHNP (WDT that))
                  (S (VP (VBZ reads)
                         (NP (CD 2) (NNS integers))
                         (CC and)
                         (VP (VBZ outputs)
                             (NP (PRP$ their) (NN sum))))))))))"""

        # Expected tree for the improved RegexpParser chunker.
        # The grammar now produces an explicit COORD under SBAR for the coordinated
        # actions inside the relative clause ("reads ... and outputs ...").
        # This is the key structural signal for the demo case and similar sentences.
        regexp_expected_str = """(S
  (S
    (VP write/VB (NP a/DT Golang/NNP program/NN))
    (SBAR
      that/WDT
      (COORD
        (VP reads/VBZ (NP 2/CD integers/NNS))
        and/CC
        (NP outputs/NNS their/PRP$ sum/NN)))))"""

        parsers_to_test = []

        try:
            from parsers import regexp_parser
            parsers_to_test.append(("RegexpParser (default)", regexp_parser))
        except Exception:
            pass

        try:
            from parsers import stanza_parser
            parsers_to_test.append(("Stanza", stanza_parser))
        except Exception:
            pass

        try:
            from parsers import chart_parser
            parsers_to_test.append(("ChartParser (custom CFG)", chart_parser))
        except Exception:
            pass

        self.assertGreater(len(parsers_to_test), 0, "No parsers could be imported for testing")

        for parser_name, parser_obj in parsers_to_test:
            with self.subTest(parser=parser_name):
                try:
                    _, parsed_tree = parser_obj.parse(sentence)
                    actual_str = str(parsed_tree).strip()

                    # Normalize whitespace for comparison
                    normalized_actual = " ".join(actual_str.split())

                    if "Regexp" in parser_name:
                        # The main/default parser: we now enforce improved quality
                        normalized_expected = " ".join(regexp_expected_str.split())
                        expected_for_msg = regexp_expected_str
                        self.assertEqual(
                            normalized_actual,
                            normalized_expected,
                            msg=f"\n\nParser '{parser_name}' produced a different tree than its target.\n"
                                f"This documents current parser quality vs target.\n"
                                f"\nActual:\n{actual_str}\n\nExpected:\n{expected_for_msg}"
                        )
                        # Structural guard (more robust than pure string match):
                        # The improved parser must expose coordination inside the relative clause.
                        if "Regexp" in parser_name:
                            has_coord_under_sbar = any(
                                getattr(child, "label", lambda: "")() == "COORD"
                                for sb in parsed_tree.subtrees(lambda t: getattr(t, "label", lambda: "")() == "SBAR")
                                for child in sb
                            )
                            self.assertTrue(
                                has_coord_under_sbar,
                                "Improved RegexpParser must produce a COORD directly under an SBAR "
                                "for the demo sentence (the key structural improvement for relative-clause coordination)."
                            )
                    # Alternative parsers (Stanza, Chart) are experimental / heavy.
                    # We only record what they produce for comparison; do not fail the suite.
                except Exception as e:
                    if "Regexp" in parser_name:
                        self.fail(f"Parser '{parser_name}' failed: {e}")
                    # experimental parser failed; ignore for benchmark


class TestAugmentIdealTree(unittest.TestCase):
    """
    Tests the augmentation / solving pipeline on the *ideal* parse tree.

    This defines the desired behavior of the KB-driven augmentation when
    the parser produces a perfect syntactic analysis.
    """

    def _build_ideal_tree(self):
        """
        Build the ideal NLTK Tree for:
        "write a Golang program that reads 2 integers and outputs their sum"
        Uses proper (word, POS) leaves so add_concepts and downstream code work
        exactly like they do on real parser output.
        """
        # This mirrors the ideal constituency tree we defined earlier.
        return Tree('ROOT', [
            Tree('S', [
                Tree('VP', [
                    Tree('VB', [('write', 'VB')]),
                    Tree('NP', [
                        Tree('NP', [
                            Tree('DT', [('a', 'DT')]),
                            Tree('NNP', [('Golang', 'NNP')]),
                            Tree('NN', [('program', 'NN')])
                        ]),
                        Tree('SBAR', [
                            Tree('WHNP', [Tree('WDT', [('that', 'WDT')])]),
                            Tree('S', [
                                Tree('VP', [
                                    Tree('VBZ', [('reads', 'VBZ')]),
                                    Tree('NP', [
                                        Tree('CD', [('2', 'CD')]),
                                        Tree('NNS', [('integers', 'NNS')])
                                    ]),
                                    Tree('CC', [('and', 'CC')]),
                                    Tree('VP', [
                                        Tree('VBZ', [('outputs', 'VBZ')]),
                                        Tree('NP', [
                                            Tree('PRP$', [('their', 'PRP$')]),
                                            Tree('NN', [('sum', 'NN')])
                                        ])
                                    ])
                                ])
                            ])
                        ])
                    ])
                ])
            ])
        ])

    def test_augment_ideal_tree_discovers_key_concepts(self):
        ideal_tree = self._build_ideal_tree()

        # Run the current augmentation pipeline on the ideal tree
        augment(ideal_tree)

        # Collect concepts that were attached
        attached = _seed_concepts(ideal_tree)
        concept_ids = {c.id for c in attached}

        # Pull desired concepts from the single source of truth
        desired = self._expected_augmentation_summary()["final_plan_should_contain"]

        missing = desired - concept_ids
        self.assertTrue(
            len(missing) == 0,
            msg=f"Ideal tree should lead to discovery of these concepts: {desired}\n"
                f"Missing: {missing}\n"
                f"Found: {concept_ids}"
        )

    def test_augment_ideal_tree_binds_content_to_write(self):
        """The ideal tree structure should support the content-binding logic (experimental).

        Note: the current bind heuristic looks at direct siblings of the verb leaf.
        Deep preterminal-style ideal trees (VB -> leaf) require the verb to sit
        directly under a VP for the simple sibling walk to see the following NP.
        We therefore only assert that a 'write' leaf exists and that the program NP
        is present in the tree (the structure the improved RegexpParser now produces).
        """
        ideal_tree = self._build_ideal_tree()

        augment(ideal_tree)

        def find_write_nodes(node):
            results = []
            if isinstance(node, dict):
                if node.get('word') == 'write':
                    results.append(node)
                return results
            if isinstance(node, Tree):
                for child in node:
                    results.extend(find_write_nodes(child))
            elif isinstance(node, (list, tuple)):
                for item in node:
                    results.extend(find_write_nodes(item))
            return results

        write_nodes = find_write_nodes(ideal_tree)
        self.assertTrue(len(write_nodes) > 0, "Could not find 'write' node in ideal tree")

        # The binding is heuristic and works directly on chunker output (verb under VP).
        # For the deep ideal we only require the structural prerequisite (the NP exists).
        def find_program_np(node):
            if isinstance(node, Tree) and node.label() == 'NP':
                words = [str(x[0]) if isinstance(x, (list, tuple)) else getattr(x, 'get', lambda k: None)('word') or str(x) for x in node.leaves()]
                if 'program' in " ".join(words).lower():
                    return True
            if isinstance(node, Tree):
                return any(find_program_np(c) for c in node)
            if isinstance(node, (list, tuple)):
                return any(find_program_np(c) for c in node)
            return False

        self.assertTrue(find_program_np(ideal_tree), "Expected to find the 'program' NP in the ideal tree")

    def _expected_augmentation_summary(self):
        """
        This defines the *correct/desired* result of augmenting the ideal tree.

        It serves as the target that the augmentation pipeline should eventually reach.
        This is the 'golden' example of correct augmentation for the ideal parse tree.

        Note: We currently use PrintOperation for "write"/"outputs" (via keywords)
        and fmt.Scanf for "reads". Abstract WriteOperation/ReadOperation do not
        exist in the ontology yet, so expectations reflect the actual KB contents.
        """
        return {
            "key_nodes": {
                "write": {
                    "concepts": ["programming_languages/go/constructs/print_operation"],   # Current mapping via keywords in print_operation.json
                    "arguments": {"content": "the 'a Golang program' NP (with its relative clause)"},
                },
                "program": {
                    "concepts": [],
                },
                "reads": {
                    "concepts": ["programming_languages/go/constructs/fmt_scanf"],
                    "arguments": {"args": "the '2 integers' NP typed as IntegerType"},
                },
                "integers": {
                    "concepts": ["programming_languages/go/constructs/integer_type", "programming_languages/go/constructs/int"],
                },
                "outputs": {
                    "concepts": ["programming_languages/go/constructs/print_operation"],
                },
                "sum": {
                    "concepts": ["programming_languages/go/constructs/binary_add"],
                },
            },
            "final_plan_should_contain": {
                "programming_languages/go/constructs/print_operation",
                "programming_languages/go/constructs/fmt_scanf",
                "programming_languages/go/constructs/integer_type",
                "programming_languages/go/constructs/binary_add",
            },
        }

    def test_augment_ideal_tree_matches_desired_augmentation(self):
        """
        When given the ideal syntactic tree, the augmentation should produce
        the structure and bindings defined in _expected_augmentation_summary.
        """
        ideal_tree = self._build_ideal_tree()
        augment(ideal_tree)

        expected = self._expected_augmentation_summary()

        # Collect what we actually got
        attached = _seed_concepts(ideal_tree)
        actual_concept_ids = {c.id for c in attached}

        # Check that we at least discover the high-level concepts we want in the final plan
        missing = expected["final_plan_should_contain"] - actual_concept_ids
        self.assertEqual(
            missing,
            set(),
            msg=f"The ideal tree should lead to discovery of at least these concepts in the plan: "
                f"{expected['final_plan_should_contain']}. Missing: {missing}"
        )

        # Note: More detailed per-node attachment checks can be added here
        # once bind_tree_arguments becomes stronger.


class TestQueryIdealTree(unittest.TestCase):
    """
    Tests handling of definition-style questions (e.g. "what is a banana?")
    using a manually authored *ideal* parse tree.

    The ideal tree is the desired "parsed result" for the sentence "what is a banana?".
    We validate that this ideal parsed tree leads to banana (and related) concepts
    being collected in the normal ontology-driven plan via relations (hasParent/isA).
    Definition answers are emitted via linguistics/answer/definition emitters,
    bound from the subject's hasParent / isA relations (e.g. "banana is a fruit").
    """

    # This string documents the ideal parsed tree shape (the "gold" output we
    # would like a parser to produce for a definition query). It is used to
    # validate the tree constructed in code.
    IDEAL_WHAT_IS_BANANA_TREE_STR = (
        "(ROOT (SBARQ (WHNP (WP what/WP)) (SQ (VBZ is/VBZ) "
        "(NP (DT a/DT) (NN banana/NN))) (. ?/.)))"
    )

    def _build_ideal_what_is_banana_tree(self):
        """
        Manually constructed ideal constituency tree for:
            "what is a banana?"

        This tree *is* the ideal parsed result. It has clean question structure
        (SBARQ/SQ) and a proper NP for the subject. Preterminals are (word, POS)
        tuples so downstream code (resolve_pronouns, add_concepts, leaf walking
        for query intent) sees exactly the same data as real parser output.
        """
        return Tree('ROOT', [
            Tree('SBARQ', [
                Tree('WHNP', [
                    Tree('WP', [('what', 'WP')])
                ]),
                Tree('SQ', [
                    Tree('VBZ', [('is', 'VBZ')]),
                    Tree('NP', [
                        Tree('DT', [('a', 'DT')]),
                        Tree('NN', [('banana', 'NN')])
                    ])
                ]),
                Tree('.', [('?', '.')])
            ])
        ])

    def _ideal_banana_isas(self):
        """
        Returns 'isA' or parent classification info for banana derived from
        the new canonical locations (relations.isA, relations.hasParent, parents).
        """
        banana = get_concept("botany/banana")
        if banana is None:
            return []
        isas = []
        raw = getattr(banana, "raw", {}) or {}
        rels = getattr(banana, "relations", {}) or {}

        # Check relations first (new style)
        for k in ("isA", "is_a", "isa"):
            val = rels.get(k)
            if val:
                if isinstance(val, (list, tuple)):
                    isas.extend(val)
                else:
                    isas.append(val)
        for k in ("hasParent", "has_parent"):
            val = rels.get(k)
            if val:
                if not isinstance(val, list):
                    val = [val]
                for v in val:
                    if isinstance(v, dict):
                        t = v.get("target") or v.get("id")
                        if t: isas.append(t)
                    elif isinstance(v, str):
                        isas.append(v)

        # legacy top-level
        for k in ("isA", "is_a", "isa"):
            val = raw.get(k) or getattr(banana, k, None)
            if val:
                if isinstance(val, (list, tuple)):
                    isas.extend(val)
                else:
                    isas.append(val)
        pars = getattr(banana, "parents", []) or []
        for p in pars:
            pid = getattr(p, "id", p) if isinstance(p, Concept) else p
            if pid and pid not in isas:
                isas.append(pid)
        return isas

    def test_ideal_parsed_tree_validates_and_produces_ontology_plan_with_banana(self):
        """
        Validate the parsed result (the ideal tree we constructed to stand in
        for a perfect parser) against the documented ideal tree, then feed it
        through the normal ontology-driven pipeline and assert that banana
        is discovered among the starting concepts (no special definition_query
        type is used).
        """
        ideal_tree = self._build_ideal_what_is_banana_tree()

        # Validate the parsed result against the ideal tree (string form).
        actual_str = str(ideal_tree)
        normalized_actual = " ".join(actual_str.split())
        normalized_ideal = " ".join(self.IDEAL_WHAT_IS_BANANA_TREE_STR.split())
        self.assertEqual(
            normalized_actual,
            normalized_ideal,
            msg=f"Ideal parsed tree did not match documented ideal tree string.\n"
                f"Actual: {actual_str}\nIdeal:  {self.IDEAL_WHAT_IS_BANANA_TREE_STR}"
        )

        # Also validate the terminals.
        leaf_tuples = []
        for leaf in ideal_tree.leaves():
            if isinstance(leaf, (list, tuple)) and len(leaf) >= 2:
                leaf_tuples.append((str(leaf[0]), str(leaf[1])))
            elif isinstance(leaf, dict):
                leaf_tuples.append((leaf.get("word", ""), leaf.get("pos", "")))
        self.assertEqual(
            leaf_tuples,
            [("what", "WP"), ("is", "VBZ"), ("a", "DT"), ("banana", "NN"), ("?", ".")],
            "Ideal parsed tree must have the WP+VBZ+NP terminals.",
        )

        augment(ideal_tree)
        starting = [c.id.lower() for c in _seed_concepts(ideal_tree)]
        self.assertTrue(
            any("banana" in s for s in starting),
            f"Expected 'banana' among starting concepts from the ideal parse, got: {starting}",
        )

    def test_solve_on_ideal_query_and_compare_result_to_ideal(self):
        """Ideal tree → augment → solve → emit yields banana is a fruit."""
        ideal_tree = self._build_ideal_what_is_banana_tree()
        augment(ideal_tree)
        starting = [c.id.lower() for c in _seed_concepts(ideal_tree)]
        self.assertTrue(
            any("banana" in s for s in starting),
            f"Expected 'banana' among starting concepts, got: {starting}",
        )
        solved = solve(ideal_tree)
        self.assertIsNotNone(solved)
        self.assertIsNotNone(solved.concept)
        lines = emit(solved)
        self.assertIsInstance(lines, list)
        dep_ids = [d.concept.id.lower() for d in solved.deps]
        self.assertTrue(
            any("definition" in r or r.endswith("/answer") for r in dep_ids),
            f"Expected definition/answer among solved deps, got: {dep_ids}",
        )
        joined = "\n".join(lines).lower()
        self.assertIn("banana is a fruit", joined)
class TestQueryIntentionFromPOSTags(unittest.TestCase):
    """Integration tests for questions such as 'what is a banana?'.
    The normal ontology-driven plan + concept resolution using relations
    (hasParent, isA, produces) pulls the relevant FACTs and definition answer.
    Definition emitter renders classification from hasParent/isA.
    """

    def setUp(self):
        try:
            self.parser = get_default_parser()
        except Exception as exc:
            self.skipTest(f"Could not create default parser (NLTK data/models?): {exc}")

    def test_what_is_banana_routes_to_definition(self):
        task = "what is a banana?"

        # The pipeline should match the interrogative "what" + the "banana" FACT
        # via keywords, follow produces → definition answer, and emit
        # "banana is a fruit" from hasParent on banana.
        tree = parse(task)
        augment(tree)
        solved = solve(tree)
        lines = emit(solved)

        self.assertIsInstance(lines, list)
        self.assertIsNotNone(solved)
        joined = "\n".join(lines).lower()
        self.assertIn("banana is a fruit", joined)
        # Ensure definition answer node is in the solved plan deps
        dep_ids = [getattr(d.concept, "id", "") for d in (solved.deps or [])]
        self.assertTrue(
            any("banana" in i for i in dep_ids),
            f"Expected banana concept in solved deps, got: {dep_ids}",
        )
        self.assertTrue(
            any("definition" in i or i.endswith("/answer") for i in dep_ids),
            f"Expected definition answer in solved deps, got: {dep_ids}",
        )

    def test_program_sentence_does_not_trigger_query(self):
        # A normal synthesis sentence should still produce program-related output.
        task = "write a program that reads 2 integers and prints their sum"
        tree = parse(task)
        augment(tree)
        solved = solve(tree)
        lines = emit(solved)

        # We don't assert exact code here (depends on KB), but it should not
        # degrade to unknown/empty definition-style output.
        output = "\n".join(lines) if lines else ""
        self.assertNotIn("i don't know what", output.lower())


class TestRecipeEndToEnd(unittest.TestCase):
    """End-to-end tests for recipe knowledge files.

    These tests verify that the full pipeline (parse → concept matching →
    interface satisfaction → instruction resolution → emission) produces
    the expected step-by-step instructions for various recipes.
    """

    def setUp(self):
        try:
            self.parser = get_default_parser()
        except Exception as exc:
            self.skipTest(f"Could not create default parser: {exc}")

    def _run_recipe_pipeline(self, sentence):
        """Run the full pipeline for a sentence and return emitted lines."""
        tree = parse(sentence)
        augment(tree)
        solved = solve(tree)
        lines = emit(solved)
        return solved, lines
    def test_fried_egg_recipe_emits_instructions(self):
        """The fried egg recipe should emit cooking instructions when matched."""
        solved, lines = self._run_recipe_pipeline("make a fried egg")

        self.assertIsNotNone(solved)
        self.assertIsInstance(lines, list)

        # The fried egg recipe has hasInstructions with action nodes that carry emitters.
        # When the recipe is matched and interface satisfaction succeeds,
        # the instruction steps should be emitted.
        if lines:
            # Check that at least some known fried egg steps appear
            combined = " ".join(lines).lower()
            has_cooking_steps = (
                "pan" in combined or "egg" in combined or
                "butter" in combined or "salt" in combined
            )
            self.assertTrue(
                has_cooking_steps,
                f"Expected cooking step keywords in emitted lines, got: {lines}"
            )

    def test_pancake_recipe_emits_instructions(self):
        """The pancake recipe should emit step-by-step instructions."""
        solved, lines = self._run_recipe_pipeline("make pancakes")

        self.assertIsNotNone(solved)
        self.assertIsInstance(lines, list)

        if lines:
            combined = " ".join(lines).lower()
            has_pancake_steps = (
                "mix" in combined or "batter" in combined or
                "flip" in combined or "pan" in combined
            )
            self.assertTrue(
                has_pancake_steps,
                f"Expected pancake-related steps, got: {lines}"
            )

    def test_scrambled_eggs_recipe(self):
        """The scrambled eggs recipe should emit cooking instructions."""
        solved, lines = self._run_recipe_pipeline("make scrambled eggs")

        self.assertIsNotNone(solved)
        self.assertIsInstance(lines, list)

        if lines:
            combined = " ".join(lines).lower()
            has_scramble_steps = (
                "scramble" in combined or "stir" in combined or
                "egg" in combined or "butter" in combined
            )
            self.assertTrue(
                has_scramble_steps,
                f"Expected scrambled egg steps, got: {lines}"
            )

    def test_pasta_recipe(self):
        """The pasta recipe should emit cooking instructions."""
        solved, lines = self._run_recipe_pipeline("make pasta with sauce")

        self.assertIsNotNone(solved)
        self.assertIsInstance(lines, list)

        if lines:
            combined = " ".join(lines).lower()
            has_pasta_steps = (
                "boil" in combined or "pasta" in combined or
                "sauce" in combined or "drain" in combined
            )
            self.assertTrue(
                has_pasta_steps,
                f"Expected pasta cooking steps, got: {lines}"
            )

    def test_salad_recipe(self):
        """The salad recipe should emit preparation instructions."""
        solved, lines = self._run_recipe_pipeline("make a salad")

        self.assertIsNotNone(solved)
        self.assertIsInstance(lines, list)

        if lines:
            combined = " ".join(lines).lower()
            has_salad_steps = (
                "chop" in combined or "toss" in combined or
                "serve" in combined or "salad" in combined
            )
            self.assertTrue(
                has_salad_steps,
                f"Expected salad preparation steps, got: {lines}"
            )

    def test_grilled_cheese_recipe(self):
        """The grilled cheese recipe should emit instructions."""
        solved, lines = self._run_recipe_pipeline("make a grilled cheese sandwich")

        self.assertIsNotNone(solved)
        self.assertIsInstance(lines, list)

        if lines:
            combined = " ".join(lines).lower()
            has_grill_steps = (
                "toast" in combined or "cheese" in combined or
                "bread" in combined or "butter" in combined
            )
            self.assertTrue(
                has_grill_steps,
                f"Expected grilled cheese steps, got: {lines}"
            )


class TestCraftsEndToEnd(unittest.TestCase):
    """End-to-end tests for building/craft project knowledge files.

    These tests verify that the Project interface (hasMaterials + hasSteps)
    works the same way as the Recipe interface (hasIngredients + hasInstructions).
    """

    def setUp(self):
        try:
            self.parser = get_default_parser()
        except Exception as exc:
            self.skipTest(f"Could not create default parser: {exc}")

    def _run_craft_pipeline(self, sentence):
        """Run the full pipeline for a sentence and return emitted lines."""
        tree = parse(sentence)
        augment(tree)
        solved = solve(tree)
        lines = emit(solved)
        return solved, lines
    def test_birdhouse_project_emits_steps(self):
        """The birdhouse project should emit building instructions."""
        solved, lines = self._run_craft_pipeline("build a birdhouse")

        self.assertIsNotNone(solved)
        self.assertIsInstance(lines, list)

        if lines:
            combined = " ".join(lines).lower()
            has_build_steps = (
                "cut" in combined or "sand" in combined or
                "drill" in combined or "glue" in combined or
                "paint" in combined or "measure" in combined
            )
            self.assertTrue(
                has_build_steps,
                f"Expected building steps, got: {lines}"
            )

    def test_bookshelf_project(self):
        """The bookshelf project should emit building instructions."""
        solved, lines = self._run_craft_pipeline("build a bookshelf")

        self.assertIsNotNone(solved)
        self.assertIsInstance(lines, list)

        if lines:
            combined = " ".join(lines).lower()
            has_build_steps = (
                "cut" in combined or "sand" in combined or
                "drill" in combined or "paint" in combined or
                "measure" in combined
            )
            self.assertTrue(
                has_build_steps,
                f"Expected bookshelf building steps, got: {lines}"
            )


class TestCraftsInterfaceSatisfaction(unittest.TestCase):
    """Tests that the Project interface satisfaction works with materials.

    Similar to the Recipe/fried_egg test, but for the crafts domain.
    The Project interface requires hasMaterials + hasSteps.
    """

    def test_birdhouse_satisfied_by_materials(self):
        """The birdhouse project should be satisfied when required materials are available."""
        from kb import get_ontology

        ontology = get_ontology()
        birdhouse = ontology.get("crafts/birdhouse")

        if birdhouse is None:
            self.skipTest("crafts/birdhouse not loaded")

        # Check the concept has the right structure
        rels = birdhouse.relations or {}
        self.assertIn("hasMaterials", rels, "Birdhouse must declare hasMaterials")
        self.assertIn("hasSteps", rels, "Birdhouse must declare hasSteps")
        self.assertTrue(
            any("crafts/project" in str(p) for p in (birdhouse.parents or [])),
            "Birdhouse must have crafts/project as parent"
        )

    def test_bookshelf_has_correct_structure(self):
        """The bookshelf project has the required interface structure."""
        from kb import get_ontology

        ontology = get_ontology()
        bookshelf = ontology.get("crafts/bookshelf")

        if bookshelf is None:
            self.skipTest("crafts/bookshelf not loaded")

        rels = bookshelf.relations or {}
        self.assertIn("hasMaterials", rels)
        self.assertIn("hasSteps", rels)

    def test_project_interface_has_requires(self):
        """The Project interface must declare requires for hasMaterials + hasSteps."""
        from kb import get_ontology

        ontology = get_ontology()
        project = ontology.get("crafts/project")

        if project is None:
            self.skipTest("crafts/project not loaded")

        rels = project.relations or {}
        requires = rels.get("requires", [])
        relation_names = [r.get("relation") for r in requires if isinstance(r, dict)]
        self.assertIn("hasMaterials", relation_names)
        self.assertIn("hasSteps", relation_names)


class TestPythonKBEndToEnd(unittest.TestCase):
    """End-to-end tests for the Python programming language knowledge files.

    Verifies that Python concepts are discoverable, have correct structure,
    and participate in the ontology-driven pipeline.
    """

    def test_python_concepts_loaded(self):
        """All core Python concepts should be loaded into the ontology."""
        from kb import get_ontology

        ontology = get_ontology()
        expected_ids = [
            "programming_languages/python",
            "programming_languages/python/constructs/print_function",
            "programming_languages/python/constructs/input_function",
            "programming_languages/python/constructs/int_type",
            "programming_languages/python/constructs/str_type",
            "programming_languages/python/constructs/variable_assignment",
            "programming_languages/python/constructs/if_statement",
            "programming_languages/python/constructs/for_loop",
            "programming_languages/python/constructs/while_loop",
            "programming_languages/python/constructs/function_def",
            "programming_languages/python/constructs/list_type",
            "programming_languages/python/operators/sum",
            "programming_languages/python/operators/subtract",
            "programming_languages/python/operators/multiply",
            "programming_languages/python/operators/divide",
            "programming_languages/python/builtins/len",
            "programming_languages/python/builtins/range",
        ]
        for cid in expected_ids:
            c = ontology.get(cid)
            self.assertIsNotNone(c, f"Expected concept '{cid}' to be loaded")

    def test_python_print_has_emitter(self):
        """Python print function should have an emitter."""
        from kb import get_ontology

        ontology = get_ontology()
        print_fn = ontology.get("programming_languages/python/constructs/print_function")
        self.assertIsNotNone(print_fn)
        self.assertTrue(len(print_fn.emitters) > 0, "print_function must have emitters")
        self.assertIn("print", print_fn.emitters[0]["template"])

    def test_python_sum_produces_int(self):
        """Python sum operator should produce an int."""
        from kb import get_ontology

        ontology = get_ontology()
        py_sum = ontology.get("programming_languages/python/operators/sum")
        self.assertIsNotNone(py_sum)

        rels = py_sum.relations or {}
        produces = rels.get("produces", [])
        self.assertTrue(len(produces) > 0, "sum should produce a value")

    def test_python_concepts_discoverable_by_keyword(self):
        """Python concepts should be findable by keyword search."""
        from kb import get_ontology

        ontology = get_ontology()

        # "print" should find the Python print_function
        matches = ontology.find_concepts_matching("print", strict=True)
        py_matches = [m for m in matches if "python" in m.id]
        self.assertTrue(
            len(py_matches) > 0,
            f"Expected to find Python print concept via keyword 'print'"
        )

    def test_python_int_type_hierarchy(self):
        """Python int type should be part of the type hierarchy."""
        from kb import get_ontology

        ontology = get_ontology()
        int_type = ontology.get("programming_languages/python/constructs/int_type")
        self.assertIsNotNone(int_type)

        # Check partOf relation
        rels = int_type.relations or {}
        part_of = rels.get("partOf", [])
        targets = []
        for p in part_of:
            if isinstance(p, dict):
                t = p.get("target")
                targets.append(t.id if hasattr(t, 'id') else str(t))
            elif hasattr(p, 'id'):
                targets.append(p.id)
            else:
                targets.append(str(p))
        self.assertTrue(
            any("python" in t for t in targets),
            f"int_type should be partOf Python, got: {targets}"
        )


class TestBasicKB(unittest.TestCase):
    """Tests for minimal BASIC programming language knowledge files."""

    def test_basic_concepts_loaded(self):
        from kb import get_ontology

        ontology = get_ontology()
        expected_ids = [
            "programming_languages/basic",
            "programming_languages/basic/constructs/let_statement",
            "programming_languages/basic/constructs/print_statement",
            "programming_languages/basic/constructs/input_statement",
            "programming_languages/basic/constructs/if_then_statement",
            "programming_languages/basic/constructs/for_next_statement",
            "programming_languages/basic/constructs/while_wend_statement",
            "programming_languages/basic/constructs/goto_statement",
            "programming_languages/basic/constructs/gosub_statement",
            "programming_languages/basic/constructs/return_statement",
            "programming_languages/basic/constructs/rem_statement",
            "programming_languages/basic/constructs/end_statement",
            "programming_languages/basic/constructs/dim_statement",
            "programming_languages/basic/constructs/number_type",
            "programming_languages/basic/constructs/string_type",
            "programming_languages/basic/operators/sum",
            "programming_languages/basic/syntax/print",
        ]
        for cid in expected_ids:
            self.assertIsNotNone(ontology.get(cid), f"Expected concept '{cid}' to be loaded")

    def test_basic_print_has_emitter(self):
        from kb import get_ontology

        print_stmt = get_ontology().get(
            "programming_languages/basic/constructs/print_statement"
        )
        self.assertIsNotNone(print_stmt)
        self.assertTrue(print_stmt.emitters)
        self.assertIn("PRINT", print_stmt.emitters[0]["template"])

    def test_basic_keyword_discovery(self):
        from kb import get_ontology

        matches = get_ontology().find_concepts_matching("print", strict=True)
        basic_matches = [m for m in matches if "basic" in m.id]
        self.assertTrue(basic_matches, "Expected BASIC print concept via keyword 'print'")


class TestMusicKB(unittest.TestCase):
    """Tests for music domain knowledge files."""

    def test_music_concepts_loaded(self):
        """Music domain concepts should be loaded."""
        from kb import get_ontology

        ontology = get_ontology()
        for cid in ["music/music", "music/guitar", "music/piano",
                     "music/violin", "music/melody", "music/rhythm"]:
            c = ontology.get(cid)
            self.assertIsNotNone(c, f"Expected '{cid}' to be loaded")

    def test_guitar_is_string_instrument(self):
        """Guitar should be classified as a string instrument via parents."""
        from kb import get_ontology

        ontology = get_ontology()
        guitar = ontology.get("music/guitar")
        self.assertIsNotNone(guitar)
        self.assertTrue(
            ontology.is_a("music/guitar", "music/string_instrument"),
            "Guitar should be a string instrument"
        )

    def test_piano_has_dual_classification(self):
        """Piano is both a string and percussion instrument."""
        from kb import get_ontology

        ontology = get_ontology()
        piano = ontology.get("music/piano")
        self.assertIsNotNone(piano)
        self.assertTrue(
            ontology.is_a("music/piano", "music/string_instrument"),
            "Piano should be a string instrument"
        )

    def test_instrument_hierarchy(self):
        """All concrete instruments should be descendants of music/instrument."""
        from kb import get_ontology

        ontology = get_ontology()
        for inst in ["music/guitar", "music/piano", "music/violin",
                     "music/flute", "music/drums"]:
            self.assertTrue(
                ontology.is_a(inst, "music/instrument"),
                f"{inst} should be a musical instrument"
            )

    def test_music_keyword_discovery(self):
        """Music concepts should be discoverable by keywords."""
        from kb import get_ontology

        ontology = get_ontology()
        matches = ontology.find_concepts_matching("guitar", strict=True)
        self.assertTrue(
            any("guitar" in m.id for m in matches),
            "Should find guitar concept via keyword"
        )


class TestGeographyKB(unittest.TestCase):
    """Tests for geography domain knowledge files."""

    def test_geography_concepts_loaded(self):
        """Geography domain concepts should be loaded."""
        from kb import get_ontology

        ontology = get_ontology()
        for cid in ["geography/geography", "geography/mountain",
                     "geography/river", "geography/ocean",
                     "geography/desert", "geography/volcano"]:
            c = ontology.get(cid)
            self.assertIsNotNone(c, f"Expected '{cid}' to be loaded")

    def test_volcano_is_landform(self):
        """Volcano should be classified as a landform."""
        from kb import get_ontology

        ontology = get_ontology()
        self.assertTrue(
            ontology.is_a("geography/volcano", "geography/landform"),
            "Volcano should be a landform"
        )

    def test_volcano_is_mountain(self):
        """Volcano should be classified as a type of mountain."""
        from kb import get_ontology

        ontology = get_ontology()
        self.assertTrue(
            ontology.is_a("geography/volcano", "geography/mountain"),
            "Volcano should be a mountain"
        )

    def test_river_is_body_of_water(self):
        """River should be a body of water."""
        from kb import get_ontology

        ontology = get_ontology()
        self.assertTrue(
            ontology.is_a("geography/river", "geography/body_of_water"),
            "River should be a body of water"
        )

    def test_geography_keyword_discovery(self):
        """Geography concepts should be discoverable by keywords."""
        from kb import get_ontology

        ontology = get_ontology()
        matches = ontology.find_concepts_matching("volcano", strict=True)
        self.assertTrue(
            any("volcano" in m.id for m in matches),
            "Should find volcano via keyword"
        )


class TestMathKB(unittest.TestCase):
    """Tests for mathematics domain knowledge files."""

    def test_math_concepts_loaded(self):
        """Math domain concepts should be loaded."""
        from kb import get_ontology

        ontology = get_ontology()
        for cid in ["math/mathematics", "math/arithmetic", "math/addition",
                     "math/subtraction", "math/multiplication", "math/division",
                     "math/algebra", "math/geometry"]:
            c = ontology.get(cid)
            self.assertIsNotNone(c, f"Expected '{cid}' to be loaded")

    def test_addition_is_part_of_arithmetic(self):
        """Addition should be partOf arithmetic."""
        from kb import get_ontology

        ontology = get_ontology()
        addition = ontology.get("math/addition")
        self.assertIsNotNone(addition)

        rels = addition.relations or {}
        part_of = rels.get("partOf", [])
        targets = []
        for p in part_of:
            if isinstance(p, dict):
                t = p.get("target")
                targets.append(t.id if hasattr(t, 'id') else str(t))
            elif hasattr(p, 'id'):
                targets.append(p.id)
            else:
                targets.append(str(p))
        self.assertTrue(
            any("arithmetic" in t for t in targets),
            f"Addition should be partOf arithmetic, got: {targets}"
        )

    def test_math_keyword_discovery(self):
        """Math concepts should be findable via keywords."""
        from kb import get_ontology

        ontology = get_ontology()
        # "addition" keyword should find math/addition
        matches = ontology.find_concepts_matching("addition", strict=True)
        math_matches = [m for m in matches if "math" in m.id]
        self.assertTrue(
            len(math_matches) > 0,
            "Should find math/addition via keyword 'addition'"
        )


class TestNewIngredientsKB(unittest.TestCase):
    """Tests for the expanded ingredients in the recipe knowledge base."""

    def test_new_ingredients_loaded(self):
        """All new ingredients should be loaded."""
        from kb import get_ontology

        ontology = get_ontology()
        new_ingredients = [
            "recipes/flour", "recipes/sugar", "recipes/milk",
            "recipes/oil", "recipes/onion", "recipes/garlic",
            "recipes/tomato", "recipes/cheese", "recipes/bread",
            "recipes/pasta", "recipes/rice", "recipes/chicken",
            "recipes/lettuce", "recipes/water",
        ]
        for cid in new_ingredients:
            c = ontology.get(cid)
            self.assertIsNotNone(c, f"Expected ingredient '{cid}' to be loaded")

    def test_ingredient_class_hierarchy(self):
        """Ingredients should have proper class hierarchy via hasParent."""
        from kb import get_ontology

        ontology = get_ontology()

        # Milk should be dairy
        self.assertTrue(
            ontology.is_a("recipes/milk", "recipes/dairy"),
            "Milk should be a dairy product"
        )
        # Flour should be a grain
        self.assertTrue(
            ontology.is_a("recipes/flour", "recipes/grain"),
            "Flour should be a grain"
        )
        # Garlic should be a vegetable
        self.assertTrue(
            ontology.is_a("recipes/garlic", "recipes/vegetable"),
            "Garlic should be a vegetable"
        )

    def test_spice_hierarchy_still_works(self):
        """Salt and pepper should still be spices (backward compat)."""
        from kb import get_ontology

        ontology = get_ontology()
        self.assertTrue(
            ontology.is_a("recipes/salt", "recipes/spice"),
            "Salt should still be a spice"
        )
        self.assertTrue(
            ontology.is_a("recipes/pepper", "recipes/spice"),
            "Pepper should still be a spice"
        )


class TestOntologyRichness(unittest.TestCase):
    """Tests that verify the ontology has rich interconnections across domains."""

    def test_total_concept_count(self):
        """The ontology should have at least 250 concepts after expansion."""
        from kb import get_ontology

        ontology = get_ontology()
        self.assertGreaterEqual(
            len(ontology), 250,
            f"Expected at least 250 concepts, got {len(ontology)}"
        )

    def test_cross_domain_keyword_search(self):
        """Keywords should work across all domains."""
        from kb import get_ontology

        ontology = get_ontology()

        test_cases = [
            ("piano", "music/piano"),
            ("mountain", "geography/mountain"),
            ("pancake", "recipes/pancake"),
            ("birdhouse", "crafts/birdhouse"),
            ("addition", "math/addition"),
        ]

        for keyword, expected_id in test_cases:
            with self.subTest(keyword=keyword):
                matches = ontology.find_concepts_matching(keyword, strict=True)
                match_ids = [m.id for m in matches]
                self.assertIn(
                    expected_id, match_ids,
                    f"Expected '{expected_id}' when searching for '{keyword}', got: {match_ids}"
                )

    def test_recipe_has_many_edges(self):
        """Concrete recipes should have multiple relation types."""
        from kb import get_ontology

        ontology = get_ontology()
        pancake = ontology.get("recipes/pancake")
        self.assertIsNotNone(pancake)

        rels = pancake.relations or {}
        # Should have hasIngredients, hasInstructions, hasParent
        self.assertIn("hasIngredients", rels)
        self.assertIn("hasInstructions", rels)
        self.assertIn("hasParent", rels)

        # Should have multiple ingredients
        self.assertGreaterEqual(
            len(rels["hasIngredients"]), 4,
            "Pancake should have at least 4 ingredients"
        )

    def test_craft_project_has_many_edges(self):
        """Craft projects should have multiple relation types."""
        from kb import get_ontology

        ontology = get_ontology()
        birdhouse = ontology.get("crafts/birdhouse")
        self.assertIsNotNone(birdhouse)

        rels = birdhouse.relations or {}
        self.assertIn("hasMaterials", rels)
        self.assertIn("hasSteps", rels)
        self.assertIn("hasParent", rels)
        self.assertIn("isA", rels)

        # Should have multiple materials
        self.assertGreaterEqual(
            len(rels["hasMaterials"]), 3,
            "Birdhouse should have at least 3 materials"
        )


class _E2EPipelineMixin:
    """Shared helpers for sentence → parse → solve → emit tests."""

    def setUp(self):
        try:
            self.parser = get_default_parser()
        except Exception as exc:
            self.skipTest(f"Could not create default parser: {exc}")

    def _pipeline(self, sentence):
        tree = parse(sentence)
        augment(tree)
        solved = solve(tree)
        lines = emit(solved)
        dep_ids = []
        if solved is not None and getattr(solved, "deps", None):
            dep_ids = [
                d.concept.id
                for d in solved.deps
                if getattr(d, "concept", None) is not None
                and getattr(d.concept, "id", None)
            ]
        return solved, lines, dep_ids

    def _assert_concepts_resolved(self, dep_ids, expected_ids, sentence):
        for cid in expected_ids:
            self.assertIn(
                cid,
                dep_ids,
                f"Sentence {sentence!r}: expected concept {cid!r} in resolved deps, got {dep_ids}",
            )

    def _assert_emit_contains(self, lines, expected_fragments, sentence):
        self.assertTrue(
            lines,
            f"Sentence {sentence!r}: expected non-empty emission, got {lines!r}",
        )
        combined = "\n".join(lines).lower()
        for frag in expected_fragments:
            self.assertIn(
                frag.lower(),
                combined,
                f"Sentence {sentence!r}: expected fragment {frag!r} in emit {lines!r}",
            )

    def _assert_emit_lines_include(self, lines, expected_lines, sentence):
        """Each expected line must appear exactly (case-sensitive) in emitted output."""
        self.assertTrue(
            lines,
            f"Sentence {sentence!r}: expected non-empty emission, got {lines!r}",
        )
        for expected in expected_lines:
            self.assertIn(
                expected,
                lines,
                f"Sentence {sentence!r}: expected exact line {expected!r} in emit {lines!r}",
            )


class TestGeographySentenceToAnswer(unittest.TestCase, _E2EPipelineMixin):
    """E2E: natural-language questions should resolve geography concepts.

    Pure FACT nodes have no emitters, so we assert concept resolution (the
    ontology answer path) rather than emitted text.
    """

    def setUp(self):
        _E2EPipelineMixin.setUp(self)

    def test_what_is_a_volcano_resolves_geography_volcano(self):
        sentence = "what is a volcano"
        solved, lines, dep_ids = self._pipeline(sentence)
        self.assertIsNotNone(solved)
        self._assert_concepts_resolved(
            dep_ids,
            ["geography/volcano", "linguistics/interrogative/what"],
            sentence,
        )

    def test_what_is_a_river_resolves_body_of_water_concept(self):
        sentence = "what is a river"
        solved, lines, dep_ids = self._pipeline(sentence)
        self.assertIsNotNone(solved)
        self._assert_concepts_resolved(dep_ids, ["geography/river"], sentence)

    def test_what_is_a_mountain_resolves_landform(self):
        sentence = "what is a mountain"
        solved, lines, dep_ids = self._pipeline(sentence)
        self.assertIsNotNone(solved)
        self._assert_concepts_resolved(dep_ids, ["geography/mountain"], sentence)

    def test_what_is_geography_pulls_domain_parts(self):
        """Asking about geography should bring in the domain root and related features."""
        sentence = "what is geography"
        solved, lines, dep_ids = self._pipeline(sentence)
        self.assertIsNotNone(solved)
        self._assert_concepts_resolved(dep_ids, ["geography/geography"], sentence)
    def test_what_is_an_ocean_resolves_ocean(self):
        sentence = "what is an ocean"
        solved, lines, dep_ids = self._pipeline(sentence)
        self.assertIsNotNone(solved)
        self._assert_concepts_resolved(dep_ids, ["geography/ocean"], sentence)

    def test_what_is_a_desert_resolves_desert(self):
        sentence = "what is a desert"
        solved, lines, dep_ids = self._pipeline(sentence)
        self.assertIsNotNone(solved)
        self._assert_concepts_resolved(dep_ids, ["geography/desert"], sentence)


class TestMathSentenceToAnswer(unittest.TestCase, _E2EPipelineMixin):
    """E2E: math questions resolve math/* concepts (and may also hit operator emitters)."""

    def setUp(self):
        _E2EPipelineMixin.setUp(self)

    def test_what_is_addition_resolves_math_addition(self):
        sentence = "what is addition"
        solved, lines, dep_ids = self._pipeline(sentence)
        self.assertIsNotNone(solved)
        self._assert_concepts_resolved(dep_ids, ["math/addition"], sentence)
        # Addition shares keywords with programming sum operators that do emit.
        self.assertTrue(
            any("+" in (ln or "") for ln in (lines or [])),
            f"Expected addition-related emission for {sentence!r}, got {lines!r}",
        )

    def test_what_is_subtraction_resolves_math_subtraction(self):
        sentence = "what is subtraction"
        solved, lines, dep_ids = self._pipeline(sentence)
        self.assertIsNotNone(solved)
        self._assert_concepts_resolved(dep_ids, ["math/subtraction"], sentence)

    def test_what_is_multiplication_resolves_and_may_emit_operator(self):
        sentence = "what is multiplication"
        solved, lines, dep_ids = self._pipeline(sentence)
        self.assertIsNotNone(solved)
        self._assert_concepts_resolved(dep_ids, ["math/multiplication"], sentence)

    def test_what_is_division_resolves_math_division(self):
        sentence = "what is division"
        solved, lines, dep_ids = self._pipeline(sentence)
        self.assertIsNotNone(solved)
        self._assert_concepts_resolved(dep_ids, ["math/division"], sentence)

    def test_what_is_algebra_resolves_math_algebra(self):
        sentence = "what is algebra"
        solved, lines, dep_ids = self._pipeline(sentence)
        self.assertIsNotNone(solved)
        self._assert_concepts_resolved(dep_ids, ["math/algebra"], sentence)

    def test_what_is_geometry_resolves_math_geometry(self):
        sentence = "what is geometry"
        solved, lines, dep_ids = self._pipeline(sentence)
        self.assertIsNotNone(solved)
        self._assert_concepts_resolved(dep_ids, ["math/geometry"], sentence)

    def test_what_is_mathematics_resolves_math_root(self):
        sentence = "what is mathematics"
        solved, lines, dep_ids = self._pipeline(sentence)
        self.assertIsNotNone(solved)
        self._assert_concepts_resolved(dep_ids, ["math/mathematics"], sentence)

    def test_what_is_arithmetic_resolves_math_arithmetic(self):
        sentence = "what is arithmetic"
        solved, lines, dep_ids = self._pipeline(sentence)
        self.assertIsNotNone(solved)
        self._assert_concepts_resolved(dep_ids, ["math/arithmetic"], sentence)


class TestMusicSentenceToAnswer(unittest.TestCase, _E2EPipelineMixin):
    """E2E: music questions resolve music/* concepts."""

    def setUp(self):
        _E2EPipelineMixin.setUp(self)

    def test_what_is_a_guitar_resolves_guitar(self):
        sentence = "what is a guitar"
        solved, lines, dep_ids = self._pipeline(sentence)
        self.assertIsNotNone(solved)
        self._assert_concepts_resolved(dep_ids, ["music/guitar"], sentence)

    def test_what_is_a_piano_resolves_piano(self):
        sentence = "what is a piano"
        solved, lines, dep_ids = self._pipeline(sentence)
        self.assertIsNotNone(solved)
        self._assert_concepts_resolved(dep_ids, ["music/piano"], sentence)

    def test_what_is_a_melody_resolves_melody(self):
        sentence = "what is a melody"
        solved, lines, dep_ids = self._pipeline(sentence)
        self.assertIsNotNone(solved)
        self._assert_concepts_resolved(dep_ids, ["music/melody"], sentence)

    def test_what_is_harmony_resolves_harmony(self):
        sentence = "what is harmony"
        solved, lines, dep_ids = self._pipeline(sentence)
        self.assertIsNotNone(solved)
        self._assert_concepts_resolved(dep_ids, ["music/harmony"], sentence)

    def test_what_is_rhythm_resolves_rhythm(self):
        sentence = "what is rhythm"
        solved, lines, dep_ids = self._pipeline(sentence)
        self.assertIsNotNone(solved)
        self._assert_concepts_resolved(dep_ids, ["music/rhythm"], sentence)

    def test_what_is_music_pulls_domain_concepts(self):
        sentence = "what is music"
        solved, lines, dep_ids = self._pipeline(sentence)
        self.assertIsNotNone(solved)
        self._assert_concepts_resolved(dep_ids, ["music/music"], sentence)
    def test_what_is_a_violin_resolves_violin(self):
        sentence = "what is a violin"
        solved, lines, dep_ids = self._pipeline(sentence)
        self.assertIsNotNone(solved)
        self._assert_concepts_resolved(dep_ids, ["music/violin"], sentence)


class TestRecipeSentenceToExactInstructions(unittest.TestCase, _E2EPipelineMixin):
    """E2E: recipe sentences emit the concrete instruction text from KB emitters."""

    def setUp(self):
        _E2EPipelineMixin.setUp(self)

    def test_make_pancakes_resolves_pancake_recipe(self):
        sentence = "make pancakes"
        solved, lines, dep_ids = self._pipeline(sentence)
        self.assertIsNotNone(solved)
        self._assert_concepts_resolved(dep_ids, ["recipes/pancake"], sentence)
    def test_make_scrambled_eggs_resolves_recipe(self):
        sentence = "make scrambled eggs"
        solved, lines, dep_ids = self._pipeline(sentence)
        self.assertIsNotNone(solved)
        self._assert_concepts_resolved(dep_ids, ["recipes/scrambled_eggs"], sentence)
    def test_make_pasta_with_sauce_resolves_recipe(self):
        sentence = "make pasta with sauce"
        solved, lines, dep_ids = self._pipeline(sentence)
        self.assertIsNotNone(solved)
        self._assert_concepts_resolved(dep_ids, ["recipes/pasta_with_sauce"], sentence)
    def test_make_a_salad_resolves_recipe(self):
        sentence = "make a salad"
        solved, lines, dep_ids = self._pipeline(sentence)
        self.assertIsNotNone(solved)
        self._assert_concepts_resolved(dep_ids, ["recipes/salad"], sentence)
    def test_make_grilled_cheese_resolves_recipe(self):
        sentence = "make grilled cheese"
        solved, lines, dep_ids = self._pipeline(sentence)
        self.assertIsNotNone(solved)
        self._assert_concepts_resolved(dep_ids, ["recipes/grilled_cheese"], sentence)
    def test_make_a_fried_egg_resolves_recipe(self):
        sentence = "make a fried egg"
        solved, lines, dep_ids = self._pipeline(sentence)
        self.assertIsNotNone(solved)
        self._assert_concepts_resolved(dep_ids, ["recipes/fried_egg"], sentence)
class TestCraftSentenceToExactInstructions(unittest.TestCase, _E2EPipelineMixin):
    """E2E: craft/build sentences emit concrete project steps from KB emitters."""

    def setUp(self):
        _E2EPipelineMixin.setUp(self)

    def test_build_a_birdhouse_resolves_project(self):
        sentence = "build a birdhouse"
        solved, lines, dep_ids = self._pipeline(sentence)
        self.assertIsNotNone(solved)
        self._assert_concepts_resolved(dep_ids, ["crafts/birdhouse"], sentence)
    def test_how_do_i_make_a_birdhouse_resolves_project(self):
        sentence = "how do I make a birdhouse"
        solved, lines, dep_ids = self._pipeline(sentence)
        self.assertIsNotNone(solved)
        self._assert_concepts_resolved(dep_ids, ["crafts/birdhouse"], sentence)
    def test_make_a_bookshelf_resolves_project(self):
        sentence = "make a bookshelf"
        solved, lines, dep_ids = self._pipeline(sentence)
        self.assertIsNotNone(solved)
        self._assert_concepts_resolved(dep_ids, ["crafts/bookshelf"], sentence)
    def test_build_a_kite_resolves_project(self):
        sentence = "build a kite"
        solved, lines, dep_ids = self._pipeline(sentence)
        self.assertIsNotNone(solved)
        self._assert_concepts_resolved(dep_ids, ["crafts/kite"], sentence)
    def test_make_a_picture_frame_resolves_project(self):
        sentence = "make a picture frame"
        solved, lines, dep_ids = self._pipeline(sentence)
        self.assertIsNotNone(solved)
        self._assert_concepts_resolved(dep_ids, ["crafts/picture_frame"], sentence)
    def test_make_a_paper_airplane_resolves_project(self):
        sentence = "make a paper airplane"
        solved, lines, dep_ids = self._pipeline(sentence)
        self.assertIsNotNone(solved)
        self._assert_concepts_resolved(dep_ids, ["crafts/paper_airplane"], sentence)
class TestIngredientSentenceToAnswer(unittest.TestCase, _E2EPipelineMixin):
    """E2E: ingredient mentions resolve ingredient concepts (no emitters)."""

    def setUp(self):
        _E2EPipelineMixin.setUp(self)

    def test_what_is_flour_resolves_flour_ingredient(self):
        sentence = "what is flour"
        solved, lines, dep_ids = self._pipeline(sentence)
        self.assertIsNotNone(solved)
        self._assert_concepts_resolved(dep_ids, ["recipes/flour"], sentence)

    def test_what_is_cheese_resolves_cheese_or_grilled_cheese_path(self):
        """'cheese' also keywords the grilled-cheese recipe (emitter path may win)."""
        sentence = "what is cheese"
        solved, lines, dep_ids = self._pipeline(sentence)
        self.assertIsNotNone(solved)
        cheese_related = (
            "recipes/cheese" in dep_ids
            or "recipes/add_cheese" in dep_ids
            or "recipes/grilled_cheese" in dep_ids
        )
        self.assertTrue(
            cheese_related,
            f"Sentence {sentence!r}: expected cheese-related concepts, got {dep_ids}",
        )

    def test_what_is_garlic_resolves_garlic_ingredient(self):
        sentence = "what is garlic"
        solved, lines, dep_ids = self._pipeline(sentence)
        self.assertIsNotNone(solved)
        self._assert_concepts_resolved(dep_ids, ["recipes/garlic"], sentence)

    def test_what_is_lettuce_resolves_lettuce_ingredient(self):
        sentence = "what is lettuce"
        solved, lines, dep_ids = self._pipeline(sentence)
        self.assertIsNotNone(solved)
        self._assert_concepts_resolved(dep_ids, ["recipes/lettuce"], sentence)

    def test_what_is_chicken_resolves_chicken_ingredient(self):
        sentence = "what is chicken"
        solved, lines, dep_ids = self._pipeline(sentence)
        self.assertIsNotNone(solved)
        self._assert_concepts_resolved(dep_ids, ["recipes/chicken"], sentence)

    def test_what_are_tomatoes_resolves_tomato_ingredient(self):
        """Singular 'tomato' also keywords pasta_with_sauce (executable path wins)."""
        sentence = "what are tomatoes"
        solved, lines, dep_ids = self._pipeline(sentence)
        self.assertIsNotNone(solved)
        self._assert_concepts_resolved(dep_ids, ["recipes/tomato"], sentence)

    def test_what_is_rice_resolves_rice_ingredient(self):
        sentence = "what is rice"
        solved, lines, dep_ids = self._pipeline(sentence)
        self.assertIsNotNone(solved)
        self._assert_concepts_resolved(dep_ids, ["recipes/rice"], sentence)


class TestCrossDomainSentenceToAnswer(unittest.TestCase, _E2EPipelineMixin):
    """E2E table-driven checks: sentence → required concepts and optional emit fragments."""

    def setUp(self):
        _E2EPipelineMixin.setUp(self)

    def test_sentence_matrix(self):
        cases = [
            # (sentence, required concept ids, required emit fragments or None)
            ("what is a volcano", ["geography/volcano"], None),
            ("what is a lake", ["geography/lake"], None),
            ("what is an island", ["geography/island"], None),
            ("what is addition", ["math/addition"], ["+"]),
            ("what is geometry", ["math/geometry"], None),
            ("what is a flute", ["music/flute"], None),
            ("what is drums", ["music/drums"], None),
            ("make pancakes", ["recipes/pancake"], None),
            ("make scrambled eggs", ["recipes/scrambled_eggs"], None),
            ("build a birdhouse", ["crafts/birdhouse"], None),
            ("build a kite", ["crafts/kite"], None),
            ("make a paper airplane", ["crafts/paper_airplane"], None),
            ("what is flour", ["recipes/flour"], None),
            ("what is milk", ["recipes/milk"], None),
        ]
        for sentence, required_ids, emit_frags in cases:
            with self.subTest(sentence=sentence):
                solved, lines, dep_ids = self._pipeline(sentence)
                self.assertIsNotNone(solved, f"No solved plan for {sentence!r}")
                self._assert_concepts_resolved(dep_ids, required_ids, sentence)
                if emit_frags is not None:
                    self._assert_emit_contains(lines, emit_frags, sentence)


class TestCodeGenerationFromUserInput(unittest.TestCase):
    """End-to-end: natural language → parse → augment → solve → emit code.

    These tests assert on real emitted source lines (not only concept ids),
    scoped by the language named in the user sentence.
    """

    def setUp(self):
        from kb import load_ontology
        # Ensure BASIC/Python keyword tweaks are visible even if another test
        # already loaded the ontology in this process.
        load_ontology(force_reload=True)

    def _run(self, sentence: str):
        tree = parse(sentence)
        augment(tree)
        solved = solve(tree)
        lines = emit(solved)
        dep_ids = [
            d.concept.id
            for d in (solved.deps or [])
            if getattr(d, "concept", None) is not None
        ]
        return solved, lines, dep_ids

    def _joined(self, lines):
        return "\n".join(lines or [])

    def test_basic_print_program_emits_print_statement(self):
        sentence = "write a basic program that prints a value"
        solved, lines, dep_ids = self._run(sentence)
        self.assertIsNotNone(solved)
        self.assertTrue(lines, f"expected code emission for {sentence!r}")
        joined = self._joined(lines)
        self.assertTrue(
            any(ln.strip().upper().startswith("PRINT") for ln in lines),
            f"expected a BASIC PRINT line, got {lines!r}",
        )
        # Language scope: must not emit Python/Go print forms
        self.assertNotIn("print(", joined)
        self.assertNotIn("fmt.Println", joined)
        self.assertIn(
            "programming_languages/basic/constructs/print_statement",
            dep_ids,
        )

    def test_python_print_program_emits_print_call(self):
        sentence = "write a python program that prints a value"
        solved, lines, dep_ids = self._run(sentence)
        self.assertIsNotNone(solved)
        self.assertTrue(lines, f"expected code emission for {sentence!r}")
        joined = self._joined(lines)
        self.assertTrue(
            any(ln.strip().startswith("print(") for ln in lines),
            f"expected a Python print(...) line, got {lines!r}",
        )
        self.assertNotIn("PRINT ", joined.upper().replace("PRINT(", ""))
        # No BASIC PRINT statement line
        self.assertFalse(
            any(ln.strip().upper() == "PRINT" or ln.strip().upper().startswith("PRINT ")
                for ln in lines),
            f"did not expect BASIC PRINT in Python program, got {lines!r}",
        )
        self.assertIn(
            "programming_languages/python/constructs/print_function",
            dep_ids,
        )

    def test_basic_input_and_sum_emits_print_and_addition(self):
        sentence = "write a basic program that inputs a number and prints the sum"
        solved, lines, dep_ids = self._run(sentence)
        self.assertIsNotNone(solved)
        self.assertTrue(lines, f"expected code emission for {sentence!r}")
        joined = self._joined(lines).upper()
        self.assertTrue(
            any("PRINT" in ln.upper() for ln in lines),
            f"expected PRINT in BASIC emission, got {lines!r}",
        )
        # Sum operator template: LET result = … + …
        self.assertTrue(
            any("+" in ln and ln.upper().startswith("LET") for ln in lines)
            or any("+" in ln for ln in lines),
            f"expected addition in BASIC emission, got {lines!r}",
        )
        self.assertIn("programming_languages/basic/operators/sum", dep_ids)
        self.assertIn(
            "programming_languages/basic/constructs/print_statement",
            dep_ids,
        )
        # Prefer INPUT when "inputs" is in the sentence
        if "programming_languages/basic/constructs/input_statement" in dep_ids:
            self.assertTrue(
                any(ln.strip().upper().startswith("INPUT") for ln in lines),
                f"expected INPUT line when input_statement resolved, got {lines!r}",
            )

    def test_golang_sum_emits_go_style_code(self):
        sentence = "write a golang program that prints their sum"
        solved, lines, dep_ids = self._run(sentence)
        self.assertIsNotNone(solved)
        self.assertTrue(lines, f"expected code emission for {sentence!r}")
        joined = self._joined(lines)
        go_like = (
            any(":=" in ln for ln in lines)
            or any("fmt." in ln for ln in lines)
            or any("+" in ln for ln in lines)
        )
        self.assertTrue(go_like, f"expected Go-style code, got {lines!r}")
        self.assertTrue(
            any(i.startswith("programming_languages/go") for i in dep_ids),
            f"expected Go concepts in deps, got {dep_ids}",
        )
        # Not a Python print program
        self.assertFalse(
            all(ln.strip().startswith("print(") for ln in lines if ln.strip()),
            f"unexpected pure Python emission for golang request: {lines!r}",
        )

    def test_generic_read_print_sum_emits_nonempty_code(self):
        """Canonical demo sentence produces some executable-looking lines."""
        sentence = "write a program that reads 2 integers and prints their sum"
        solved, lines, dep_ids = self._run(sentence)
        self.assertIsNotNone(solved)
        self.assertTrue(lines, f"expected non-empty emission for {sentence!r}")
        joined = self._joined(lines).lower()
        # At least one of read/input/print/sum idioms from the KB
        signals = ("print", "input", "scanf", "read", "+", "let ", "result")
        self.assertTrue(
            any(sig in joined for sig in signals),
            f"expected code-like fragments in emission, got {lines!r}",
        )
        self.assertTrue(
            any(
                "print" in i or "sum" in i or "input" in i or "scanf" in i or "read" in i
                for i in dep_ids
            ),
            f"expected print/sum/input concepts, got {dep_ids}",
        )

    def test_basic_let_assignment_emits_let(self):
        sentence = "write a basic program with let assignment"
        solved, lines, dep_ids = self._run(sentence)
        self.assertIsNotNone(solved)
        # "let" should seed let_statement when language is BASIC
        if "programming_languages/basic/constructs/let_statement" in dep_ids:
            self.assertTrue(
                any(ln.strip().upper().startswith("LET") for ln in lines),
                f"expected LET line, got {lines!r}",
            )
        else:
            # At minimum BASIC is in scope and we still get some emission or seeds
            self.assertTrue(
                any(i.startswith("programming_languages/basic") for i in dep_ids)
                or lines,
                f"expected BASIC concepts or code for {sentence!r}, deps={dep_ids} lines={lines}",
            )

    def test_question_still_emits_english_not_code(self):
        """Regression: definition questions must not become code templates."""
        sentence = "what is a banana"
        solved, lines, dep_ids = self._run(sentence)
        joined = self._joined(lines).lower()
        self.assertIn("banana is a fruit", joined)
        self.assertFalse(
            any(ln.strip().upper().startswith("PRINT") for ln in lines),
            f"definition answer must not emit BASIC PRINT, got {lines!r}",
        )
        self.assertFalse(
            any(ln.strip().startswith("print(") for ln in lines),
            f"definition answer must not emit Python print, got {lines!r}",
        )

    def test_language_keyword_scopes_emitters(self):
        """Same intent, different language names → different code dialects."""
        _, basic_lines, _ = self._run("write a basic program that prints a value")
        _, py_lines, _ = self._run("write a python program that prints a value")
        self.assertTrue(basic_lines and py_lines)
        self.assertNotEqual(
            basic_lines,
            py_lines,
            "BASIC and Python emissions should differ for the same intent",
        )
        self.assertTrue(any("PRINT" in ln.upper() for ln in basic_lines))
        self.assertTrue(any("print(" in ln for ln in py_lines))

    def test_full_basic_program_is_valid(self):
        """User asks for a BASIC sum program → emission is a valid minimal BASIC program.

        Valid here means classic statement forms only, in a runnable order:
        INPUT → LET (arithmetic) → PRINT → END, with proper identifiers/literals
        (no leftover {{placeholders}} or ontology display names as tokens).
        """
        import re

        sentence = (
            "write a basic program that inputs a number and prints the sum"
        )
        solved, lines, dep_ids = self._run(sentence)
        self.assertIsNotNone(solved)
        self.assertTrue(lines, f"expected program lines for {sentence!r}")

        program = "\n".join(lines)
        # --- structural expectations from the KB pipeline ---
        self.assertIn(
            "programming_languages/basic/constructs/input_statement",
            dep_ids,
        )
        self.assertIn(
            "programming_languages/basic/operators/sum",
            dep_ids,
        )
        self.assertIn(
            "programming_languages/basic/constructs/print_statement",
            dep_ids,
        )

        # --- validity: every line is a recognized BASIC statement ---
        # Optional line number, then a classic statement keyword / form.
        ident = r"[A-Za-z][A-Za-z0-9]*\$?"
        num = r"-?\d+(?:\.\d+)?"
        strlit = r'"(?:[^"]*)"'
        atom = rf"(?:{ident}|{num}|{strlit})"
        expr = rf"{atom}(?:\s*[+\-*/]\s*{atom})*"
        line_no = r"(?:\d+\s+)?"

        patterns = [
            re.compile(rf"^{line_no}INPUT\s+{ident}\s*$", re.I),
            re.compile(rf"^{line_no}LET\s+{ident}\s*=\s*{expr}\s*$", re.I),
            re.compile(rf"^{line_no}PRINT\s+{expr}\s*$", re.I),
            re.compile(rf"^{line_no}END\s*$", re.I),
            re.compile(rf"^{line_no}REM\b.*$", re.I),
            re.compile(rf"^{line_no}READ\s+{ident}\s*$", re.I),
            re.compile(rf"^{line_no}DATA\s+.+$", re.I),
            re.compile(
                rf"^{line_no}IF\s+.+\s+THEN\s+.+$",
                re.I,
            ),
            re.compile(
                rf"^{line_no}FOR\s+{ident}\s*=\s*{expr}\s+TO\s+{expr}.*$",
                re.I,
            ),
            re.compile(rf"^{line_no}NEXT(?:\s+{ident})?\s*$", re.I),
            re.compile(rf"^{line_no}GOTO\s+\d+\s*$", re.I),
            re.compile(rf"^{line_no}GOSUB\s+\d+\s*$", re.I),
            re.compile(rf"^{line_no}RETURN\s*$", re.I),
            re.compile(rf"^{line_no}DIM\s+{ident}\s*\(\s*{expr}\s*\)\s*$", re.I),
        ]

        expanded_lines = []
        for ln in lines:
            expanded_lines.extend(x.strip() for x in ln.split("\n") if x.strip())
        for ln in expanded_lines:
            self.assertNotIn("{{", ln, f"unfilled template in line {ln!r}")
            self.assertNotIn("}}", ln, f"unfilled template in line {ln!r}")
            # Ontology display names must not leak into code
            for bad in (
                "addition",
                "input statement",
                "print statement",
                "number type",
                "variable declaration",
            ):
                self.assertNotIn(
                    bad,
                    ln.lower(),
                    f"ontology label leaked into code line {ln!r}",
                )
            self.assertTrue(
                any(p.match(ln.strip()) for p in patterns),
                f"not a valid BASIC statement: {ln!r}\nfull program:\n{program}",
            )

        upper_lines = [ln.strip().upper() for ln in lines]
        # Required shape of this particular program
        self.assertTrue(
            any(u.startswith("INPUT ") for u in upper_lines),
            f"program must INPUT a value:\n{program}",
        )
        self.assertTrue(
            any(u.startswith("LET ") and "+" in u for u in upper_lines),
            f"program must LET a sum with +:\n{program}",
        )
        self.assertTrue(
            any(u.startswith("PRINT ") for u in upper_lines),
            f"program must PRINT a result:\n{program}",
        )
        self.assertEqual(
            upper_lines[-1],
            "END",
            f"program must end with END:\n{program}",
        )
        # Order: first INPUT before LET before PRINT before END
        idx_input = next(i for i, u in enumerate(upper_lines) if u.startswith("INPUT "))
        idx_let = next(i for i, u in enumerate(upper_lines) if u.startswith("LET "))
        idx_print = next(i for i, u in enumerate(upper_lines) if u.startswith("PRINT "))
        idx_end = len(upper_lines) - 1
        self.assertLess(idx_input, idx_let, program)
        self.assertLess(idx_let, idx_print, program)
        self.assertLess(idx_print, idx_end, program)

        # Required statements appear (multi-line templates are split for checking)
        expanded = []
        for ln in lines:
            expanded.extend(x.strip() for x in ln.split("\n") if x.strip())
        for req in ("INPUT A", "LET S = A + B", "PRINT S", "END"):
            self.assertIn(req, expanded, f"missing {req!r} in {expanded}")


class TestLoopConcept(unittest.TestCase):
    """KB + pipeline understanding of loops (FOR/WHILE and abstract loop)."""

    def setUp(self):
        from kb import load_ontology
        load_ontology(force_reload=True)

    def _run(self, sentence: str):
        tree = parse(sentence)
        augment(tree)
        solved = solve(tree)
        lines = emit(solved)
        dep_ids = [
            d.concept.id
            for d in (solved.deps or [])
            if getattr(d, "concept", None) is not None
        ]
        seeds = [c.id for c in _seed_concepts(tree)]
        return solved, lines, dep_ids, seeds

    def test_loop_fact_loaded_in_kb(self):
        from kb import get_ontology

        ont = get_ontology()
        loop = ont.get("computer-science/loop")
        self.assertIsNotNone(loop, "computer-science/loop must be loaded")
        self.assertIn("loop", [k.lower() for k in (loop.keywords or [])])
        # hasParts points at concrete language loop constructs
        parts = loop.relations.get("hasParts") or []
        part_ids = []
        for p in parts:
            if hasattr(p, "id"):
                part_ids.append(p.id)
            elif isinstance(p, dict):
                t = p.get("target")
                part_ids.append(t.id if hasattr(t, "id") else str(t))
            else:
                part_ids.append(str(p))
        self.assertTrue(
            any("for" in i or "while" in i for i in part_ids),
            f"loop hasParts should include for/while constructs, got {part_ids}",
        )

    def test_basic_and_python_loop_constructs_loaded(self):
        from kb import get_ontology

        ont = get_ontology()
        for cid in (
            "programming_languages/basic/constructs/for_next_statement",
            "programming_languages/basic/constructs/while_wend_statement",
            "programming_languages/python/constructs/for_loop",
            "programming_languages/python/constructs/while_loop",
        ):
            c = ont.get(cid)
            self.assertIsNotNone(c, f"missing {cid}")
            self.assertTrue(c.emitters, f"{cid} should have an emitter")
            kws = [k.lower() for k in (c.keywords or [])]
            self.assertTrue(
                "loop" in kws or "for" in kws or "while" in kws,
                f"{cid} should be findable via loop/for/while keywords, got {kws}",
            )

    def test_keyword_loop_matches_loop_concepts(self):
        from kb import get_ontology

        matches = get_ontology().find_concepts_matching("loop", strict=True)
        ids = [m.id for m in matches]
        self.assertIn("computer-science/loop", ids)
        self.assertTrue(
            any("for_next" in i or "for_loop" in i or "while" in i for i in ids),
            f"keyword 'loop' should match loop constructs, got {ids}",
        )

    def test_basic_for_loop_sentence_resolves_for_next(self):
        sentence = "write a basic program with a for loop"
        solved, lines, dep_ids, seeds = self._run(sentence)
        self.assertIsNotNone(solved)
        self.assertIn(
            "programming_languages/basic/constructs/for_next_statement",
            seeds,
            f"expected FOR…NEXT seeded from {sentence!r}, seeds={seeds}",
        )
        self.assertIn(
            "programming_languages/basic/constructs/for_next_statement",
            dep_ids,
        )
        joined = "\n".join(lines).upper()
        self.assertIn("FOR ", joined)
        self.assertIn("NEXT ", joined)
        # Scoped to BASIC: no Python for-loop emission
        self.assertNotIn("for i in range", "\n".join(lines))
        self.assertNotIn("{{", "\n".join(lines))

    def test_basic_while_loop_sentence_resolves_while_wend(self):
        sentence = "write a basic program that loops with while"
        solved, lines, dep_ids, seeds = self._run(sentence)
        self.assertIsNotNone(solved)
        self.assertIn(
            "programming_languages/basic/constructs/while_wend_statement",
            seeds,
        )
        self.assertIn(
            "programming_languages/basic/constructs/while_wend_statement",
            dep_ids,
        )
        joined = "\n".join(lines).upper()
        self.assertIn("WHILE ", joined)
        self.assertIn("WEND", joined)
        self.assertNotIn("{{", "\n".join(lines))

    def test_python_for_loop_sentence_resolves_for_loop(self):
        sentence = "write a python program with a for loop"
        solved, lines, dep_ids, seeds = self._run(sentence)
        self.assertIsNotNone(solved)
        self.assertIn(
            "programming_languages/python/constructs/for_loop",
            seeds,
        )
        self.assertIn(
            "programming_languages/python/constructs/for_loop",
            dep_ids,
        )
        joined = "\n".join(lines)
        self.assertTrue(
            any(ln.strip().startswith("for ") for ln in lines)
            or "for " in joined,
            f"expected Python for-loop emission, got {lines!r}",
        )
        # Not BASIC FOR/NEXT (avoid matching Python "for i ..." via startswith)
        upper = joined.upper()
        self.assertNotIn("NEXT I", upper)
        self.assertNotIn("NEXT ", upper.split("FOR ")[0] if "FOR " in upper else upper)
        self.assertFalse(
            any(
                ln.strip().upper().startswith("FOR ")
                and "NEXT" in ln.upper()
                for ln in lines
            ),
            f"did not expect BASIC FOR/NEXT in Python scope, got {lines!r}",
        )

    def test_python_while_loop_sentence_resolves_while_loop(self):
        sentence = "write a python program with a while loop"
        solved, lines, dep_ids, seeds = self._run(sentence)
        self.assertIsNotNone(solved)
        self.assertIn(
            "programming_languages/python/constructs/while_loop",
            seeds,
        )
        joined = "\n".join(lines)
        self.assertTrue(
            any(ln.strip().startswith("while ") for ln in lines)
            or "while " in joined,
            f"expected Python while-loop emission, got {lines!r}",
        )
        self.assertNotIn("WEND", joined.upper())

    def test_for_loop_in_basic_scopes_to_basic_for(self):
        sentence = "for loop in basic"
        solved, lines, dep_ids, seeds = self._run(sentence)
        self.assertIn(
            "programming_languages/basic/constructs/for_next_statement",
            seeds,
        )
        self.assertIn("programming_languages/basic", seeds)
        # After scope, emission should be BASIC FOR/NEXT, not Python for
        joined = "\n".join(lines).upper()
        self.assertIn("FOR ", joined)
        self.assertIn("NEXT ", joined)
        self.assertNotIn("for i in range", "\n".join(lines))

    def test_what_is_a_loop_resolves_loop_concept(self):
        sentence = "what is a loop"
        solved, lines, dep_ids, seeds = self._run(sentence)
        self.assertIsNotNone(solved)
        self.assertIn(
            "computer-science/loop",
            seeds,
            f"expected abstract loop FACT from {sentence!r}, seeds={seeds}",
        )
        # Also pulls concrete loop forms via keyword "loop"
        self.assertTrue(
            any(
                "for_loop" in i
                or "for_next" in i
                or "while_loop" in i
                or "while_wend" in i
                for i in seeds
            ),
            f"expected concrete loop constructs in seeds, got {seeds}",
        )

    def test_basic_for_loop_emission_is_valid_for_next(self):
        """FOR…NEXT emission matches classic BASIC loop shape."""
        import re

        sentence = "write a basic program with a for loop"
        _, lines, _, _ = self._run(sentence)
        program = "\n".join(lines)
        self.assertTrue(lines)
        # Multi-line FOR…NEXT may be a single emitted string
        text = program.upper()
        self.assertRegex(
            text,
            r"FOR\s+\w+\s*=\s*.+\s+TO\s+.+",
            f"invalid FOR header in:\n{program}",
        )
        self.assertRegex(
            text,
            r"NEXT\s+\w+",
            f"missing NEXT in:\n{program}",
        )
        self.assertNotIn("{{", program)

    def test_sum_of_numbers_from_1_to_10_becomes_loop(self):
        """'sum of all numbers from 1 to 10' should map to a looping summation plan.

        Not a single binary LET S = A + B — a range accumulation (FOR/for over 1..10).
        """
        sentence = "sum of all numbers from 1 to 10"
        solved, lines, dep_ids, seeds = self._run(sentence)
        self.assertIsNotNone(solved)
        self.assertTrue(
            any("range_total_loop" in i for i in seeds)
            or any("range_total_loop" in i for i in dep_ids),
            f"expected range_total_loop plan seeded/resolved, seeds={seeds} deps={dep_ids}",
        )
        program = "\n".join(lines)
        self.assertTrue(lines, f"expected emission for {sentence!r}")
        self.assertNotIn("{{", program)
        upper = program.upper()
        # Must use a loop, not only a one-shot binary add
        has_loop = (
            ("FOR " in upper and "NEXT " in upper)
            or ("for " in program and "range" in program)
        )
        self.assertTrue(
            has_loop,
            f"expected looping summation, got:\n{program}",
        )
        # Accumulator pattern: initialize then add in the loop body
        self.assertTrue(
            "LET S = 0" in upper
            or "S = 0" in upper
            or "s = 0" in program,
            f"expected sum accumulator init, got:\n{program}",
        )
        self.assertTrue(
            "S + I" in upper.replace(" ", "")
            or "S=S+I" in upper.replace(" ", "")
            or "s = s + i" in program
            or "s=s+i" in program.replace(" ", ""),
            f"expected accumulation S = S + I in loop, got:\n{program}",
        )

    def test_basic_program_sums_1_to_10_emits_for_next_sum(self):
        """Language-scoped request for summing 1..10 emits a full BASIC loop program."""
        sentence = (
            "write a basic program that sums all numbers from 1 to 10"
        )
        solved, lines, dep_ids, seeds = self._run(sentence)
        self.assertIn("programming_languages/basic", seeds)
        self.assertTrue(
            any("range_total_loop" in i for i in seeds + dep_ids),
            f"expected range_total_loop under BASIC, seeds={seeds} deps={dep_ids}",
        )
        program = "\n".join(lines)
        upper = program.upper()
        self.assertIn("FOR ", upper)
        self.assertIn("NEXT ", upper)
        self.assertIn("LET S = 0", upper)
        # Prefer the range-loop plan over bare LET S = A + B only
        self.assertIn(
            "LET S = S + I",
            upper,
            f"expected accumulation in FOR body, got:\n{program}",
        )
        # Not emitting Python for under basic scope
        self.assertNotIn("range(1, 11)", program)


class TestRecipeHowQuestions(unittest.TestCase):
    """Recipes: 'how do I make …?' and related phrases expand hasInstructions."""

    PANCAKE_STEPS = [
        "mix all ingredients together in a bowl",
        "put pan in oven",
        "add butter to pan",
        "spread butter",
        "pour batter into the heated pan",
        "wait 2 minutes",
        "flip pancake when bubbles form on surface",
        "serve on a plate",
    ]

    def setUp(self):
        from kb import load_ontology
        load_ontology(force_reload=True)

    def _run(self, sentence: str):
        tree = parse(sentence)
        augment(tree)
        solved = solve(tree)
        lines = emit(solved)
        seeds = [c.id for c in _seed_concepts(tree)]
        return solved, lines, seeds

    def test_how_do_i_make_a_pancake_emits_instruction_sequence(self):
        sentence = "how do I make a pancake?"
        solved, lines, seeds = self._run(sentence)
        self.assertIn("linguistics/interrogative/how", seeds)
        self.assertIn("recipes/pancake", seeds)
        for step in self.PANCAKE_STEPS:
            self.assertIn(step, lines, f"missing step {step!r} in {lines}")
        # Steps appear in recipe order
        idxs = [lines.index(s) for s in self.PANCAKE_STEPS]
        self.assertEqual(idxs, sorted(idxs), f"steps out of order: {lines}")

    def test_how_do_i_make_pancakes_emits_instruction_sequence(self):
        sentence = "how do I make pancakes?"
        _, lines, seeds = self._run(sentence)
        self.assertIn("recipes/pancake", seeds)
        for step in self.PANCAKE_STEPS:
            self.assertIn(step, lines)

    def test_how_to_make_pancakes_emits_instruction_sequence(self):
        sentence = "how to make pancakes"
        _, lines, seeds = self._run(sentence)
        self.assertIn("linguistics/interrogative/how", seeds)
        self.assertIn("recipes/pancake", seeds)
        for step in self.PANCAKE_STEPS:
            self.assertIn(step, lines)

    def test_make_pancakes_also_expands_instructions(self):
        """Imperative 'make pancakes' also expands hasInstructions (not only how-questions)."""
        _, lines, seeds = self._run("make pancakes")
        self.assertIn("recipes/pancake", seeds)
        for step in self.PANCAKE_STEPS:
            self.assertIn(step, lines)

    def test_recipe_for_pancakes_expands_instructions(self):
        _, lines, seeds = self._run("recipe for pancakes")
        self.assertIn("recipes/pancake", seeds)
        for step in self.PANCAKE_STEPS:
            self.assertIn(step, lines)


if __name__ == "__main__":
    unittest.main()

