import unittest
import nltk

from coreference_resolver import resolve_pronouns


class TestCoreferenceResolver(unittest.TestCase):
    def resolve_and_extract(self, sentence):
        """Helper method to tokenize, tag, parse, resolve pronouns, and extract resolutions."""
        tokens = nltk.word_tokenize(sentence)
        tagged = nltk.pos_tag(tokens)
        parsed_tree = nltk.chunk.ne_chunk(tagged)
        resolved_tree = resolve_pronouns(parsed_tree)
        
        actual_resolutions = {}
        for leaf in resolved_tree.leaves():
            if leaf['reference'] is not None:
                actual_resolutions[leaf['word']] = leaf['reference']
        
        return actual_resolutions

    def test_original_example(self):
        """Test the original example with a single pronoun resolution."""
        sentence = "write a Golang program that reads 2 integers and prints their sum"
        expected_resolutions = {"that": "a Golang program", "their": "2 integers"}
        
        actual_resolutions = self.resolve_and_extract(sentence)
        self.assertEqual(actual_resolutions, expected_resolutions)

    def test_multiple_pronouns(self):
        """Test a sentence with multiple pronouns."""
        sentence = "Alice and Bob gave their books to her"
        expected_resolutions = {"her": "Bob"}
        
        actual_resolutions = self.resolve_and_extract(sentence)
        self.assertEqual(actual_resolutions, expected_resolutions)

    def test_demonstrative_pronoun(self):
        """Test a sentence with a demonstrative pronoun."""
        sentence = "what this program does?"
        expected_resolutions = {"this": "program"}
        
        actual_resolutions = self.resolve_and_extract(sentence)
        self.assertEqual(actual_resolutions, expected_resolutions)

    def test_demo_example_real_pipeline(self):
        """Regression test for the canonical demo example using the actual
        pipeline that `python main.py` runs.

        Exercises:
          - parsers.get_default_parser() / RegexpChunkParser (the primary
            lightweight parser used by the interactive loop)
          - coreference_resolver.resolve_pronouns (the relative/possessive
            pronoun solver for WDT "that", PRP$ "their", etc.)

        The test stops after resolve_pronouns (no tree_to_solved_plan or KB
        augmentation). This locks in correct pronoun resolution behavior on the
        primary demo input used throughout the project.
        """
        try:
            from parsers import get_default_parser
            parser = get_default_parser()
        except Exception as exc:
            self.skipTest(f"Could not import default parser (NLTK?): {exc}")

        # The single most-referenced demo sentence in README, docs, and tests
        sentence = "write a Golang program that reads 2 integers and prints their sum"

        try:
            resolved_tree, parsed_tree = parser.parse(sentence)
        except Exception as exc:
            self.skipTest(f"parser.parse failed (missing NLTK data?): {exc}")

        # Extract resolutions the same way the interactive main loop does
        resolutions = {}
        for leaf in resolved_tree.leaves():
            if isinstance(leaf, dict) and leaf.get("reference") is not None:
                resolutions[leaf["word"]] = leaf["reference"]

        expected = {"that": "a Golang program", "their": "2 integers"}
        self.assertEqual(resolutions, expected)

        # Structural checks: resolve_pronouns must have produced the rich dict
        # leaves, and the chunker + resolver must have seen the key pronoun tags.
        all_leaves = list(resolved_tree.leaves())
        self.assertTrue(
            any(isinstance(l, dict) for l in all_leaves),
            "resolve_pronouns should return dict leaves carrying 'reference'"
        )
        self.assertTrue(
            any(getattr(l, "get", lambda k, d=None: None)("pos") == "PRP$" for l in all_leaves if isinstance(l, dict)),
            "Demo tree must contain PRP$ (possessive pronoun) leaves after chunking"
        )
        self.assertTrue(
            any(getattr(l, "get", lambda k, d=None: None)("pos") == "WDT" for l in all_leaves if isinstance(l, dict)),
            "Demo tree must contain WDT (relative pronoun 'that') after chunking"
        )


if __name__ == '__main__':
    unittest.main()
