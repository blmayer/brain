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


if __name__ == '__main__':
    unittest.main()
