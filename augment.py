"""Augment parsed natural language into executable plans.

Flow:
1. Parse sentence → tagged tree (via NLTK + coref).
2. Map words/actions from the tree to Concepts in the ontology (kb/ontology/).
3. Recursively resolve dependencies (e.g. "prints" → Print concept → fmt.Println → its required arguments).
4. Bind variables and emit code using the resolved Concepts' emitters.
"""

import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Union

from kb import Concept, get_concept, get_ontology
from logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class ExecNode:
    """Runtime execution node using the new ontology format."""
    concept: Concept
    bindings: Dict[str, str] = field(default_factory=dict)
    deps: List["ExecNode"] = field(default_factory=list)


@dataclass
class Context:
    """Binding context for names during solve (shared across tree)."""
    bindings: Dict[str, str] = field(default_factory=dict)
    types: Dict[str, str] = field(default_factory=dict)  # actual_name -> type e.g. "a" -> "int"
    counter: int = 0

    def bind(self, logical: str, typ: str, preferred: Optional[str] = None) -> str:
        if logical in self.bindings:
            return self.bindings[logical]
        self.counter += 1
        if preferred:
            actual = preferred
        else:
            base = typ if typ not in ("any", "type") else "v"
            actual = f"{base}{self.counter}"
        self.bindings[logical] = actual
        if typ not in ("any", "type"):
            self.types[actual] = typ
        return actual

    def get_type(self, name: str) -> str:
        return self.types.get(name, "any")


# _is_leaf_plan removed - no longer needed in ontology-native flow


def solve_plan(plan: Any, ctx: Optional[Context] = None, providing: Any = None) -> ExecNode:
    """
    Ontology-native solver.
    Walks plans produced by the new dependency-resolution flow.
    """
    logger.debug("Entering solve_plan with plan type: %s", plan.get("type") if isinstance(plan, dict) else type(plan))
    if ctx is None:
        ctx = Context()

    if isinstance(plan, dict):
        plan_type = plan.get("type")

        if plan_type == "ontology_driven_plan":
            # New flow: we already have the resolved concepts from dependency resolution
            resolved = plan.get("all_concepts", [])
            program_concept = get_concept("FunctionDeclaration") or Concept(
                id="Program", kind="Program", name="Main Program"
            )
            root = ExecNode(concept=program_concept)

            for concept in resolved:
                if isinstance(concept, Concept):
                    root.deps.append(ExecNode(concept=concept))

            return root

        if plan_type == "sum_program":
            # Temporary fallback for the older structure during transition
            steps = plan.get("steps", [])
            program_concept = get_concept("FunctionDeclaration") or Concept(
                id="Program", kind="Program", name="Main Program"
            )
            root = ExecNode(concept=program_concept)
            for step in steps:
                step_concept = step.get("concept")
                if isinstance(step_concept, Concept):
                    root.deps.append(ExecNode(concept=step_concept, bindings=step))
            return root

        fb = get_concept("FunctionDeclaration") or Concept(id="Unknown", kind="Unknown", name="Unknown")
        return ExecNode(concept=fb)

    fb = get_concept("FunctionDeclaration") or Concept(id="Fallback", kind="Fallback", name="Fallback")
    return ExecNode(concept=fb)

# Legacy solve_plan body completely removed.
# We are now fully on the new ontology-native flow.


def render(concept: Concept, bindings: Dict[str, str]) -> str:
    """Render a Concept using its emitters and the current bindings."""
    logger.debug("Rendering concept: %s", getattr(concept, 'id', 'unknown'))
    if not concept or not concept.emitters:
        return f"// no emitter defined for {getattr(concept, 'id', 'unknown')}"

    template = concept.emitters[0].get("template", "")

    def replacer(match):
        key = match.group(1).strip()
        return str(bindings.get(key, key))

    import re
    return re.sub(r"\{\{([^}]+)\}\}", replacer, template)


def emit(exec_n: ExecNode, visited: Optional[Dict[str, bool]] = None, out: Optional[List[str]] = None) -> List[str]:
    """DFS post-order emit using the new ontology format."""
    logger.debug("Entering emit for concept: %s", getattr(exec_n.concept, 'id', 'unknown'))

    if visited is None:
        visited = {}
    if out is None:
        out = []

    key = getattr(exec_n.concept, 'id', 'unknown') + str(id(exec_n))
    if visited.get(key):
        return out
    visited[key] = True

    for d in exec_n.deps:
        emit(d, visited, out)

    line = render(exec_n.concept, exec_n.bindings)
    if line:
        logger.debug("Emitting line: %s", line)
        out.append(line)

    return out


def _make_key(e: ExecNode) -> str:
    key = e.node.id
    for k, v in sorted(e.bindings.items()):
        key += f"|{k}={v}"
    return key


# Legacy plan-building helpers (make_plan / make_var_plan) and the old demo
# have been removed. We now use the ontology-native flow exclusively.


# ------------------------------------------------------------------
# Generic bridge: NLTK POS-tagged / NE trees (from process_input in main.py)
#                       → intent features → Plan → solved ExecNode
#
# Detection of actions is now driven by the KB itself:
#   for every verb (and noun) in the tree we check whether a normalized
#   form exists as a key in KB.  No hardcoded verb lists anywhere.
# ------------------------------------------------------------------

def _leaf_to_dict(leaf):
    """Normalize any leaf (raw (word,pos) tuple or resolved dict) to a uniform dict."""
    if isinstance(leaf, dict):
        return leaf
    if isinstance(leaf, (list, tuple)) and len(leaf) >= 2:
        return {'word': str(leaf[0]), 'pos': str(leaf[1]), 'reference': None}
    return {'word': str(leaf), 'pos': 'UNK', 'reference': None}


def _walk_leaves(tree):
    """Yield normalized leaf dicts from an nltk.Tree (or list of subtrees)."""
    if tree is None:
        return
    if isinstance(tree, (list, tuple)):
        for item in tree:
            yield from _walk_leaves(item)
        return
    if isinstance(tree, dict):
        yield tree
        return
    # nltk.Tree or Tree-like
    try:
        for raw in tree.leaves():
            yield _leaf_to_dict(raw)
    except Exception:
        for child in getattr(tree, 'children', getattr(tree, '', [])):
            yield from _walk_leaves(child)


def _normalize_to_concept_id(word: str) -> str:
    """Light normalization for concept lookup in the new ontology."""
    w = word.lower().strip()
    ontology = get_ontology()

    if w in ontology.concepts:
        return w

    for suffix in ('s', 'es', 'ies'):
        if w.endswith(suffix):
            base = w[:-len(suffix)]
            if base in ontology.concepts:
                return base
            if suffix == 'ies' and (base + 'y') in ontology.concepts:
                return base + 'y'
    return w


def _extract_intent_features(tree) -> dict:
    """Generic, KB-driven feature extraction.

    Walks the tree, and for every verb/noun checks whether a normalized
    form is present as a key in the Knowledge Base.  This makes the
    detector automatically support any new templates you add to KB
    (e.g. 'loop', 'if', 'sort', 'filter'...) without changing this code.
    """
    logger.debug("Extracting intent features from tree...")
    words, pos_tags, lower_words = [], [], []

    for leaf in _walk_leaves(tree):
        w = leaf.get('word', '')
        p = leaf.get('pos', '')
        words.append(w)
        pos_tags.append(p)
        lower_words.append(w.lower())

    text = ' '.join(lower_words)

    # Collect interesting words for concept matching
    verbs = [w for w, p in zip(words, pos_tags)
             if isinstance(p, str) and p.startswith('VB')]
    nouns = [w for w, p in zip(words, pos_tags)
             if isinstance(p, str) and p.startswith(('NN', 'JJ', 'NNP'))]  # include adjectives and proper nouns

    # Also include some key words like "program", "code" etc. from the full text
    interesting_words = verbs + nouns + [w for w in lower_words if w in ("program", "code", "script", "read", "print", "sum", "add", "write")]

    # Ontology-driven detection (new format)
    detected_concepts = set()
    ontology = get_ontology()
    for w in interesting_words:
        cid = _normalize_to_concept_id(w)
        if cid in ontology.concepts:
            detected_concepts.add(cid)

    features = {
        'verbs': verbs,
        'nouns': nouns,
        'text': text,
        'has_program': any(k in text for k in ('program', 'code', 'script')),
        'languages': [],
        'detected_concepts': detected_concepts,
        'io_verbs': set(),
        'arithmetic': set(),
        'input_count_hint': 2,
    }

    # Language hints (still a small static map – can be moved to KB later)
    lang_hints = {'go': 'golang', 'golang': 'golang', 'python': 'python', 'py': 'python'}
    for w in lower_words:
        if w in lang_hints:
            features['languages'].append(lang_hints[w])

    # Classify detected concepts into higher-level action buckets
    for cid in detected_concepts:
        cl = cid.lower()
        if any(x in cl for x in ['read', 'scanf', 'input', 'scan']):
            features['io_verbs'].add('read')
        if any(x in cl for x in ['print', 'output', 'write']):
            features['io_verbs'].add('print')
        if any(x in cl for x in ['sum', 'add', 'addition', 'plus', 'binary']):
            features['arithmetic'].add('sum')

    # Fallback numeric hint (unchanged, very lightweight)
    for i, w in enumerate(lower_words):
        if w.isdigit():
            try:
                n = int(w)
                if 1 <= n <= 10:
                    window = ' '.join(lower_words[i+1:i+4])
                    if any(k in window for k in ('integer', 'number', 'int', 'num')):
                        features['input_count_hint'] = n
            except ValueError:
                pass

    return features


def _map_features_to_initial_concepts(features: dict) -> list[Concept]:
    """
    Piece 1 of the new flow (purely data-driven):

    Process each word from the tagged tree *separately*.
    For every individual word, find concepts that match it (mainly via the 'keywords' field).

    Concepts are then ranked by how many individual words triggered them.
    This allows "prints" and "sum" to independently surface their respective concepts.

    For now we return the full ranked list (callers can take the top one or more).
    """
    ontology = get_ontology()
    verbs = features.get('verbs', [])
    nouns = features.get('nouns', [])

    # Collect candidate words (verbs + nouns)
    candidate_words = []
    for w in verbs + nouns:
        w = w.lower().strip()
        if len(w) > 2:
            candidate_words.append(w)

    if not candidate_words:
        logger.info("Concept discovery found 0 initial concepts (no candidate words)")
        return []

    # Per-word matching + frequency counting
    from collections import defaultdict
    concept_scores = defaultdict(int)

    for word in candidate_words:
        matches = ontology.find_concepts_matching(word, strict=True)
        for concept in matches:
            concept_scores[concept.id] += 1

    if not concept_scores:
        logger.info("Concept discovery found 0 initial concepts")
        return []

    # Rank by number of triggering words (descending)
    ranked = sorted(
        [(ontology.get(cid), score) for cid, score in concept_scores.items() if ontology.get(cid)],
        key=lambda x: -x[1]
    )

    initial_concepts = [c for c, score in ranked]

    logger.info("Concept discovery found %d unique concepts (ranked by word match count)", len(initial_concepts))
    if logger.isEnabledFor(logging.DEBUG):
        debug_list = [f"{c.id}({score})" for c, score in ranked[:8]]
        logger.debug("Top concepts by matches: %s", debug_list)

    return initial_concepts


def _resolve_dependencies(starting_concepts: list[Concept], max_depth: int = 4) -> list[Concept]:
    """
    Proper dependency satisfaction (the requested piece #2).

    Given starting concepts, recursively resolves what they need by walking
    relations and looking for producers of required types.
    """
    ontology = get_ontology()
    resolved: list[Concept] = []
    seen = set()

    logger.info("Starting dependency resolution for %d concepts", len(starting_concepts))

    def can_produce(concept: Concept, required_type: str) -> bool:
        """Quick check if this concept can satisfy a type requirement."""
        rels = concept.relations or {}
        for prod in rels.get("produces", []):
            if isinstance(prod, dict):
                if prod.get("type", "").lower() in (required_type.lower(), "any"):
                    logger.debug("      %s can produce type '%s'", concept.id, required_type)
                    return True
            elif isinstance(prod, str) and prod.lower() == required_type.lower():
                logger.debug("      %s can produce type '%s'", concept.id, required_type)
                return True
        return False

    def collect_needs(concept: Concept) -> list[dict]:
        """Extract typed needs/parameters from a concept's relations."""
        needs = []
        rels = concept.relations or {}

        for rel_name in ["needs", "hasParameter"]:
            items = rels.get(rel_name, [])
            if isinstance(items, dict):
                items = [items]
            for item in items:
                if isinstance(item, dict):
                    needs.append({
                        "name": item.get("name", "arg"),
                        "type": item.get("type", "any")
                    })

        if needs:
            logger.debug("    %s has %d needs: %s", concept.id, len(needs), needs)
        return needs

    def recurse(concept: Concept, depth: int, context: list[Concept]):
        if depth > max_depth or concept.id in seen:
            return
        seen.add(concept.id)
        resolved.append(concept)

        logger.debug("  [%d] Resolving concept: %s", depth, concept.id)

        needs = collect_needs(concept)

        for need in needs:
            req_type = need["type"]

            satisfied = False
            for prev in context + resolved:
                if can_produce(prev, req_type):
                    satisfied = True
                    break

            if not satisfied:
                candidates = ontology.find_producers_of_type(req_type)

                # Be much stricter with 'any' — only use it as a last resort
                if req_type == "any":
                    # Only consider very specific producers for 'any' (e.g. actual function calls or declarations)
                    candidates = [c for c in candidates if c.kind in ("BUILTIN", "SYNTACTIC_CONSTRUCT") and "Declaration" in c.id or "Call" in c.id]

                if candidates:
                    logger.debug("    Need '%s' (%s) → found %d candidate producers",
                                 need['name'], req_type, len(candidates))
                    for cand in candidates:
                        if cand.id not in seen:
                            recurse(cand, depth + 1, context + [concept])

        # Follow structural + implementation relations
        related = ontology.find_related_concepts(
            concept,
            relation_names=["importsPackage", "implementedBy", "relatedTo", "specializes"]
        )
        for rel in related:
            recurse(rel, depth + 1, context + [concept])

        # Explicitly look for concrete implementations of this concept
        implementations = ontology.find_implementations_of(concept.id)
        for impl in implementations:
            if impl.id not in seen:
                recurse(impl, depth + 1, context + [concept])

    for c in starting_concepts:
        recurse(c, 0, [])

    # Remove duplicates while preserving order
    seen = set()
    unique_resolved = []
    for c in resolved:
        if c.id not in seen:
            seen.add(c.id)
            unique_resolved.append(c)

    # Prefer concrete implementations over abstract ones when both exist
    final = []
    for c in unique_resolved:
        impls = ontology.find_implementations_of(c.id)
        if impls:
            final.extend(impls)
        else:
            final.append(c)

    # Dedup again after preferring implementations
    seen = set()
    deduped = []
    for c in final:
        if c.id not in seen:
            seen.add(c.id)
            deduped.append(c)

    logger.info("Dependency resolution complete. Resolved %d concepts total", len(deduped))
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("Resolved concepts: %s", [c.id for c in deduped])

    return deduped


def _features_to_plan(features: dict) -> dict:
    """
    New ontology-driven planning (in progress).
    Uses concept lookup + dependency resolution instead of hardcoded legacy nodes.
    """
    get_ontology()

    logger.info("Building ontology-driven plan...")

    initial_concepts = _map_features_to_initial_concepts(features)
    resolved_concepts = _resolve_dependencies(initial_concepts)

    logger.info(
        "Plan built with %d starting concepts and %d resolved dependencies",
        len(initial_concepts), len(resolved_concepts)
    )
    logger.debug("_features_to_plan completed")

    return {
        "type": "ontology_driven_plan",
        "starting_concepts": [c.id for c in initial_concepts],
        "resolved_dependencies": [c.id for c in resolved_concepts],
        "all_concepts": resolved_concepts,
    }


def tree_to_solved_plan(parsed_tree, resolved_tree=None):
    """Public entry point (new ontology-native path)."""
    logger.info("Starting tree-to-plan conversion")
    get_ontology()
    logger.debug("tree_to_solved_plan called")
    tree = resolved_tree if resolved_tree is not None else parsed_tree
    features = _extract_intent_features(tree)
    plan = _features_to_plan(features)
    ctx = Context()
    solved = solve_plan(plan, ctx)
    logger.info("tree_to_solved_plan completed")
    return solved
