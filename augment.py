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

import nltk

from kb import Concept, get_concept, get_ontology
from logging_config import get_logger
from coreference_resolver import resolve_pronouns

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
# Generic bridge: NLTK POS-tagged / NE trees (from any Parser in parsers.py)
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


def add_concepts(tree) -> None:
    """Modify the tree **in place** by attaching matching ontology Concepts to its nodes.

    For each leaf we normalize the word and search the ontology.
    Matching Concept objects are stored directly on the leaf under the key
    'concepts' (as a list).

    Raw NLTK leaves (word, pos) tuples are converted to dict form so that
    the annotations can be attached while preserving the overall tree shape.
    """
    ontology = get_ontology()

    def attach_to_leaf(leaf_dict: dict, word: str):
        """Normalize and attach concepts to a single leaf dict."""
        if not isinstance(word, str) or not word.strip():
            leaf_dict['concepts'] = []
            return

        normalized = _normalize_to_concept_id(word)
        matches = ontology.find_concepts_matching(normalized, strict=True)
        leaf_dict['concepts'] = matches or []

    def process(node: Any):
        if node is None:
            return

        # Already a dict leaf (common after resolve_pronouns)
        if isinstance(node, dict):
            w = node.get('word', '')
            attach_to_leaf(node, w)
            return

        # nltk.Tree (or anything with children)
        if isinstance(node, nltk.Tree):
            for i in range(len(node)):
                child = node[i]
                if isinstance(child, nltk.Tree):
                    process(child)
                else:
                    # Leaf: either tuple (word, pos) or already a dict
                    if isinstance(child, dict):
                        w = child.get('word', '')
                        attach_to_leaf(child, w)
                    elif isinstance(child, (list, tuple)) and len(child) >= 2:
                        word = str(child[0])
                        pos = str(child[1])
                        normalized = _normalize_to_concept_id(word)
                        matches = ontology.find_concepts_matching(normalized, strict=True)
                        # Replace the raw leaf with a rich dict so we can carry ontology nodes
                        node[i] = {
                            'word': word,
                            'pos': pos,
                            'reference': None,
                            'concepts': matches or []
                        }
                    else:
                        # Unexpected leaf form — wrap it
                        w = str(child)
                        node[i] = {
                            'word': w,
                            'pos': 'UNK',
                            'reference': None,
                            'concepts': []
                        }
            return

        # Generic sequence (should be rare at top level)
        if isinstance(node, (list, tuple)):
            for item in node:
                process(item)

    process(tree)

    logger.debug("add_concepts finished annotating tree with ontology concepts")


def bind_tree_arguments(tree):
    """
    Structural argument binding (early experiment).

    After concepts have been attached to leaves, this function looks at the
    tree structure to bind arguments to verb concepts.

    Current heuristics:
    - For a verb that has concepts with 'hasParameter', look at the following
      NP sibling(s) inside the same VP/COORD and record them as potential
      argument values (especially 'content').
    - For "that" (relative clause), link the preceding NP to the following
      clause (COORD or VP) so the dependency solver can see the description
      of the head noun.
    """
    ontology = get_ontology()

    def has_content_need(concept: Concept) -> bool:
        rels = concept.relations or {}
        for item in rels.get("hasParameter", []):
            if isinstance(item, dict) and item.get("name") == "content":
                return True
        return False

    def process(node, parent=None, siblings=None):
        if isinstance(node, dict):
            # Leaf
            word = node.get("word", "").lower()
            pos = node.get("pos", "")

            # Handle relative "that" / "which"
            if pos in ("WDT", "WP") and word in ("that", "which"):
                # Find nearest preceding NP (the head) among siblings
                if siblings:
                    for i, sib in enumerate(siblings):
                        if sib is node:
                            # Look backwards for an NP
                            for j in range(i - 1, -1, -1):
                                prev = siblings[j]
                                if isinstance(prev, dict) and prev.get("pos", "").startswith("NN"):
                                    # Attach following material (if any) as description of this NP
                                    following = siblings[i+1:] if i+1 < len(siblings) else []
                                    if following:
                                        prev.setdefault("relative_clause", []).extend(following)
                                    break
                            break
                return

            # Verb argument binding (very early heuristic)
            concepts = node.get("concepts", [])
            for c in concepts:
                if has_content_need(c):
                    # Look for a following NP in the local siblings (inside VP)
                    if siblings:
                        idx = None
                        for i, s in enumerate(siblings):
                            if s is node:
                                idx = i
                                break
                        if idx is not None:
                            for j in range(idx + 1, len(siblings)):
                                nxt = siblings[j]
                                if isinstance(nxt, dict) and nxt.get("pos", "").startswith(("NN", "CD")):
                                    node.setdefault("arguments", {})["content"] = nxt
                                    break
                                if isinstance(nxt, nltk.Tree) and nxt.label() == "NP":
                                    node.setdefault("arguments", {})["content"] = nxt
                                    break
                            else:
                                # Also try one level up if we are inside a preterminal (VB/VBZ etc)
                                # e.g. ideal trees have (VP (VB (write-dict)) (NP ...))
                                if parent is not None and hasattr(parent, "label"):
                                    parent_label = parent.label()
                                    if parent_label.startswith(("VB", "VBP", "VBZ")):
                                        grand = getattr(parent, "_parent", None)  # not set, so walk via caller's parent? skip complex
                                        pass
            return

        if isinstance(node, nltk.Tree):
            label = node.label() if hasattr(node, "label") else ""
            children = list(node)

            # Recurse on children, passing siblings for local context
            for i, child in enumerate(children):
                process(child, parent=node, siblings=children)

            # Special case: if this is a VP or COORD containing a verb + following material,
            # we already handled most binding inside the leaf recursion above.
            return

        if isinstance(node, (list, tuple)):
            for item in node:
                process(item)

    process(tree)
    logger.debug("bind_tree_arguments completed structural attachment")


def _collect_concepts_from_tree(tree) -> list[Concept]:
    """Collect ontology Concepts that were previously attached to the tree
    by add_concepts (looks for the 'concepts' key on leaves).

    Returns concepts in the order they first appear, with duplicates removed.
    """
    seen = set()
    collected: list[Concept] = []

    for leaf in _walk_leaves(tree):
        for c in leaf.get('concepts', []):
            if isinstance(c, Concept) and c.id not in seen:
                seen.add(c.id)
                collected.append(c)

    return collected


def format_tree(tree, prefix: str = "", is_last: bool = True, show_concepts: bool = True, max_concepts: int = 3) -> str:
    """
    Return a pretty string representation of the (possibly annotated) tree.

    Shows the NLTK syntactic structure + any ontology concepts that were
    attached by add_concepts (under the 'concepts' key on leaves).
    """
    lines = []

    def _concept_str(c: Concept) -> str:
        return c.id

    def _format_leaf(leaf: dict) -> str:
        word = leaf.get('word', '?')
        pos = leaf.get('pos', '')
        ref = leaf.get('reference')
        parts = [f'"{word}"']
        if pos:
            parts.append(f"({pos})")
        if ref:
            parts.append(f"→ {ref}")

        text = " ".join(parts)

        if show_concepts:
            concepts = leaf.get('concepts', []) or []
            if concepts:
                names = [_concept_str(c) for c in concepts[:max_concepts]]
                extra = f" +{len(concepts) - max_concepts}" if len(concepts) > max_concepts else ""
                text += f"  [concepts: {', '.join(names)}{extra}]"

            # Show structural bindings when present
            args = leaf.get('arguments')
            if args:
                text += f"  [args: {list(args.keys())}]"

            rel = leaf.get('relative_clause')
            if rel:
                text += "  [rel_clause]"
        return text

    def _recurse(node: Any, prefix: str, is_last: bool, is_root: bool = False):
        if is_root:
            connector = ""
        else:
            connector = "└── " if is_last else "├── "

        if isinstance(node, dict):
            # Leaf (after our normalization)
            line = prefix + connector + _format_leaf(node)
            lines.append(line)
            return

        if isinstance(node, nltk.Tree):
            # Internal node
            label = node.label() if hasattr(node, 'label') else str(node)
            line = prefix + connector + f"[{label}]"
            lines.append(line)

            children = list(node)
            new_prefix = prefix + ("    " if (is_last or is_root) else "│   ")
            for i, child in enumerate(children):
                _recurse(child, new_prefix, i == len(children) - 1)
            return

        # Fallback for raw tuples or other forms
        if isinstance(node, (list, tuple)) and len(node) >= 2 and not isinstance(node[0], (dict, nltk.Tree)):
            word, pos = str(node[0]), str(node[1])
            fake_leaf = {'word': word, 'pos': pos}
            line = prefix + connector + _format_leaf(fake_leaf)
            lines.append(line)
            return

        # Unknown node type
        line = prefix + connector + f"<{type(node).__name__}: {str(node)[:60]}>"
        lines.append(line)

    _recurse(tree, prefix, is_last, is_root=True)
    return "\n".join(lines)


def pretty_print_tree(tree, **kwargs):
    """Convenience wrapper around format_tree that prints to stdout."""
    print(format_tree(tree, prefix="", is_last=True, **kwargs))


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


def _features_to_plan(tree) -> dict:
    """
    New ontology-driven planning.

    Takes a parsed tree directly. It first mutates the tree via add_concepts
    (attaching ontology nodes under 'concepts' on the leaves), then collects
    those attached concepts to drive the rest of planning + dependency resolution.
    """
    get_ontology()

    logger.info("Building ontology-driven plan...")

    add_concepts(tree)                                   # mutates tree in place
    bind_tree_arguments(tree)                            # structural argument binding
    initial_concepts = _collect_concepts_from_tree(tree)
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
    """Public entry point (new ontology-native path).

    Ensures relative/possessive pronouns (PRP$, WDT, WP, etc.) are resolved
    via resolve_pronouns() *before* any augmentation steps (_features_to_plan
    calls add_concepts + bind_tree_arguments). This makes the function safe
    to call directly with raw parser output.
    """
    logger.info("Starting tree-to-plan conversion")
    get_ontology()
    logger.debug("tree_to_solved_plan called")

    if resolved_tree is None:
        resolved_tree = resolve_pronouns(parsed_tree)
    tree = resolved_tree

    plan = _features_to_plan(tree)
    ctx = Context()
    solved = solve_plan(plan, ctx)
    logger.info("tree_to_solved_plan completed")
    return solved
