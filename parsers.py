"""Parser interface and implementations for the Brain natural language input pipeline.

All parsers implement the same `Parser` interface and return:
    (resolved_tree, raw_parsed_tree)

This makes them interchangeable for coreference, augmentation, KB-driven planning,
and code emission. The default (RegexpChunkParser) is lightweight and sufficient
for the program's descriptive sentences the system targets.
"""

from abc import ABC, abstractmethod
from typing import Tuple, Any, Optional

import nltk
from nltk.chunk import RegexpParser

from coreference_resolver import resolve_pronouns


# =============================================================================
# Default: RegexpParser-based chunker (lightweight, pragmatic)
# =============================================================================

# Grammar for shallow syntactic chunking using NLTK's RegexpParser.
#
# This is a pragmatic regex-based chunker (not a full parser).
# It is designed to produce better structure than ne_chunk for our use case:
# sentences describing programs ("write a program that reads X and does Y").
#
# Key improvements:
# - Better handling of coordination ("and" + second action) both at top level
#   and *inside relative clauses* (e.g. "a program that reads X and prints Y").
# - Tolerance for common POS tagger errors (e.g. "prints" tagged as NNS instead of VBZ).
# - Improved NP coverage (possessives like "their").
# - Explicit COORD nodes under SBAR for coordinated actions in relative clauses.
#   This gives downstream logic (coref, bind_tree_arguments, planners) a clear
#   signal for "the described program performs these steps".
#
# The rule *order* is deliberate: VP and COORD rules run first so that
# coordination inside "that ..." can be recognized before the SBAR rule
# wraps the relative clause. The primary SBAR pattern then prefers
# structured content (COORD / VP) after the relativizer.
CHUNK_GRAMMAR = r'''
    NP: {<DT|JJ|NN.*|CD|PRP\$>+}          # Noun phrases (incl. numbers, adjectives, possessives)

    PP: {<IN><NP>}                         # Prepositional phrases

    # === Verb Phrases ===
    VP: {<VB.*><NP|PP>*}                   # Normal verb + objects/modifiers

    # === Coordinated Structures ===
    # Rules to recognize the second verb phrase after "and" / "or".
    # Multiple variants are needed because the POS tagger frequently mis-tags
    # the second verb in coordinated structures (e.g. "prints" becomes NNS).
    VP: {<CC><VB.*><NP|PP>*}               # "and" + correctly tagged verb
    VP: {<CC><NN.*><NP|PP>*}               # "and" + verb mistagged as noun ("prints", "writes", etc.)

    # This is the most important rule for creating a connection between the two sides.
    # It groups "VP and VP" (or "VP and NP" as fallback) into a single COORD node.
    # This gives us an explicit link between "reads 2 integers" and "prints their sum"
    # even when they appear inside a relative clause attached to "program".
    COORD: {<VP><CC><VP>}                  # Best case: two proper VPs connected by "and"
    COORD: {<VP><CC><NP>}                  # Common fallback when second side is still an NP
    COORD: {<VP><CC><NN.*>}                # Loose fallback for heavily mistagged second verb

    # === Relative clauses (SBAR) ===
    # Primary rule prefers structured content after the relativizer so that
    # a COORD (or VP) built by the earlier rules becomes a child of the SBAR.
    # This is what lets "program that reads X and prints Y" expose the two
    # actions as a COORD under the SBAR under the program NP.
    SBAR: {<WDT|WP> <COORD|VP|S>}          # Structured relative clause (COORD/VP after WDT)
    SBAR: {<WDT|WP><.*>+}                  # Fallback (original greedy behavior for other cases)

    # Attach the relative clause to the immediately preceding NP ("program that..." -> NP with SBAR child)
    # This produces structure much closer to full parsers (the modifier is nested under the head).
    NP: {<NP><SBAR>}

    CLAUSE: {<NP><VP|SBAR|COORD>}
    CLAUSE: {<NP><COORD>}
    S: {<VP|NP><VP|NP|SBAR|COORD>*}
'''


class Parser(ABC):
    """Abstract interface for text-to-tree parsers.

    Every implementation must return a (resolved_tree, raw_parsed_tree) pair.
    The resolved_tree has had pronouns resolved via resolve_pronouns (leaves
    become dicts with 'word', 'pos', 'reference'). The raw_parsed_tree is the
    direct output of the underlying syntactic parser/chunker.

    This contract lets any parser be dropped into the rest of the pipeline
    (augment.tree_to_solved_plan, main loop, tests) without changes.
    """

    @abstractmethod
    def parse(self, text: str) -> Tuple[Any, Any]:
        """Return (resolved_tree, parsed_tree) for the given natural language text."""
        raise NotImplementedError


class RegexpChunkParser(Parser):
    """Default parser: NLTK RegexpParser with a domain-tuned chunk grammar.

    Lightweight (no Java, no large downloads), fast, and produces the
    coordination-under-SBAR structures that the ontology planner relies on
    for relative-clause program descriptions.
    """

    def __init__(self) -> None:
        self.chunker = RegexpParser(CHUNK_GRAMMAR)

    def parse(self, text: str) -> Tuple[Any, Any]:
        tokens = nltk.word_tokenize(text)
        tagged = nltk.pos_tag(tokens)
        parsed_tree = self.chunker.parse(tagged)
        resolved_tree = resolve_pronouns(parsed_tree)
        return resolved_tree, parsed_tree


# =============================================================================
# Alternative: Custom CFG + ChartParser (pure NLTK, no external dependencies)
# =============================================================================

from nltk import CFG
from nltk.parse import ChartParser

# Small domain-specific grammar designed to capture relative clauses ("that")
# and coordination ("and") better than RegexpParser chunking.
PROGRAM_GRAMMAR = CFG.fromstring("""
    S -> VP
    VP -> VB NP | VBZ NP | VBP NP
    VP -> VP CC VP
    NP -> DT JJ NNP NN
    NP -> DT NNP NN
    NP -> DT NN
    NP -> CD NNS
    NP -> PossPron NN
    SBAR -> IN S
    NP -> NP SBAR
    CC -> 'and'
    IN -> 'that'
    VB -> 'write'
    VBZ -> 'reads' | 'outputs' | 'prints'
    VBP -> 'do' | 'does'
    DT -> 'a' | 'the' | '2'
    JJ -> 'golang'
    NNP -> 'golang'
    NN -> 'program' | 'sum' | 'integer'
    NNS -> 'integers'
    CD -> '2'
    PossPron -> 'their'
""")


class ChartParser(Parser):
    """Alternative using NLTK's ChartParser with a tiny custom CFG.

    Produces proper hierarchical trees (especially good for relative clauses
    with "that" and verb coordination with "and"). The grammar is intentionally
    small and will fail or degrade on inputs outside its vocabulary.
    """

    def __init__(self) -> None:
        self._chart_parser: Optional[Any] = None

    def _get_chart_parser(self):
        if self._chart_parser is None:
            self._chart_parser = ChartParser(PROGRAM_GRAMMAR)
        return self._chart_parser

    def parse(self, text: str) -> Tuple[Any, Any]:
        parser = self._get_chart_parser()
        tokens = nltk.word_tokenize(text.lower())

        parses = list(parser.parse(tokens))
        if not parses:
            # Graceful fallback
            from nltk.tree import Tree
            parsed_tree = Tree('S', [Tree('X', tokens)])
        else:
            parsed_tree = parses[0]

        resolved_tree = resolve_pronouns(parsed_tree)
        return resolved_tree, parsed_tree


# =============================================================================
# CoreNLP Alternative Path
# =============================================================================

class CoreNLPParser(Parser):
    """Stanford CoreNLP parser (full constituency + good coordination handling).

    Lazily starts a CoreNLPServer on first use (requires Java; first run
    downloads models). Reuses the server across calls.
    """

    def __init__(self) -> None:
        self._corenlp_server = None
        self._corenlp_parser = None

    def _get_corenlp_parser(self):
        """Lazily starts a CoreNLPServer and returns a CoreNLPParser."""
        if self._corenlp_parser is not None:
            return self._corenlp_parser

        from nltk.parse.corenlp import CoreNLPServer, CoreNLPParser as NLTKCoreNLPParser

        if self._corenlp_server is None:
            print("[CoreNLP] Starting Stanford CoreNLP server (first run may download models)...")
            self._corenlp_server = CoreNLPServer()
            self._corenlp_server.start()

        self._corenlp_parser = NLTKCoreNLPParser(url=self._corenlp_server.url)
        return self._corenlp_parser

    def parse(self, text: str) -> Tuple[Any, Any]:
        parser = self._get_corenlp_parser()
        parsed_tree = next(parser.raw_parse(text))
        resolved_tree = resolve_pronouns(parsed_tree)
        return resolved_tree, parsed_tree


# =============================================================================
# Stanza (Modern, Java-free Stanford NLP)
# =============================================================================

class StanzaParser(Parser):
    """Stanza pipeline (pure-Python-friendly Stanford NLP with constituency parsing).

    Downloads models on first use. Enables constituency + coref processors
    but still applies the project's resolve_pronouns for uniformity.
    """

    def __init__(self) -> None:
        self._stanza_pipeline = None

    def _get_stanza_pipeline(self):
        """Lazily initializes and returns a Stanza pipeline with constituency parsing."""
        if self._stanza_pipeline is not None:
            return self._stanza_pipeline

        import stanza

        print("[Stanza] Downloading English model (first run only)...")
        stanza.download('en', verbose=False)

        self._stanza_pipeline = stanza.Pipeline(
            lang='en',
            processors='tokenize,pos,lemma,depparse,constituency,coref',
            package={
                'constituency': 'default_accurate',
                'depparse': 'default_accurate',
                'coref': 'default_accurate'
            },
            verbose=False,
            use_gpu=False,           # Set to True if you have a GPU
        )
        print("[Stanza] Pipeline ready.")
        return self._stanza_pipeline

    def _stanza_tree_to_nltk(self, stanza_tree):
        """Recursively convert a Stanza constituency Tree to an NLTK Tree."""
        from nltk.tree import Tree as NLTKTree

        if stanza_tree.is_leaf():
            return stanza_tree.label  # just the word

        children = [self._stanza_tree_to_nltk(child) for child in stanza_tree.children]
        return NLTKTree(stanza_tree.label, children)

    def parse(self, text: str) -> Tuple[Any, Any]:
        nlp = self._get_stanza_pipeline()
        doc = nlp(text)

        # Stanza returns a Document; we take the first sentence
        sent = doc.sentences[0]

        if sent.constituency:
            parsed_tree = self._stanza_tree_to_nltk(sent.constituency)
        else:
            # Fallback: build a very basic tree from words
            from nltk.tree import Tree as NLTKTree
            words = [word.text for word in sent.words]
            parsed_tree = NLTKTree('S', words)

        resolved_tree = resolve_pronouns(parsed_tree)
        return resolved_tree, parsed_tree


# =============================================================================
# Public API / discovery helpers
# =============================================================================

# Pre-instantiated singletons for easy import and reuse (parsers are stateless)
regexp_parser: Parser = RegexpChunkParser()
chart_parser: Parser = ChartParser()
corenlp_parser: Parser = CoreNLPParser()
stanza_parser: Parser = StanzaParser()


def get_default_parser() -> Parser:
    """Return the recommended default parser (lightweight Regexp chunker)."""
    return regexp_parser
