"""Augment parsed natural language into executable plans.

Flow:
1. Parse sentence → tagged tree (via NLTK + coref).
2. Map words/actions from the tree to Concepts in the KB (loaded from kb/programming_languages/).
3. Recursively resolve dependencies (e.g. "prints" → Print concept → fmt.Println → its required arguments).
4. Bind variables and emit code using the resolved Concepts' emitters.
"""

import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Union

import nltk

from kb import Concept, get_concept, get_ontology, Ontology
from logging_config import get_logger
from coreference_resolver import resolve_pronouns

logger = get_logger(__name__)


@dataclass
class ExecNode:
    """Runtime execution node using the new ontology format."""
    concept: Concept
    bindings: Dict[str, str] = field(default_factory=dict)
    deps: List["ExecNode"] = field(default_factory=list)


# _is_leaf_plan removed - no longer needed in ontology-native flow


def solve_plan(plan: Any) -> ExecNode:
    """
    Ontology-native solver.
    Walks plans produced by the new dependency-resolution flow.
    """
    logger.debug("Entering solve_plan with plan type: %s", plan.get("type") if isinstance(plan, dict) else type(plan))

    if isinstance(plan, dict):
        plan_type = plan.get("type")

        if plan_type == "ontology_driven_plan":
            # New flow: we already have the resolved concepts from dependency resolution
            resolved = plan.get("all_concepts", [])
            # If we are emitting a list of executable steps (from satisfied interface
            # instructions), use a silent root so we do not emit an extra "func ..."
            # wrapper line from the codegen-oriented FunctionDeclaration.
            has_executable_steps = any(
                (isinstance(c, Concept) and (c.kind == "ACTION" or bool(getattr(c, "emitters", None))))
                for c in resolved
            )
            if has_executable_steps:
                program_concept = Concept(id="ExecutionList", kind="EXEC", name="Execution List")
                # no emitters => render will produce nothing for the root
            else:
                program_concept = get_concept("programming_languages/go/constructs/function_declaration") or Concept(
                    id="Program", kind="Program", name="Main Program"
                )
            root = ExecNode(concept=program_concept)

            for concept in resolved:
                if isinstance(concept, Concept):
                    root.deps.append(ExecNode(concept=concept))

            return root

        fb = get_concept("programming_languages/go/constructs/function_declaration") or Concept(id="Unknown", kind="Unknown", name="Unknown")
        return ExecNode(concept=fb)

    fb = get_concept("programming_languages/go/constructs/function_declaration") or Concept(id="Fallback", kind="Fallback", name="Fallback")
    return ExecNode(concept=fb)

# Legacy solve_plan body completely removed.
# We are now fully on the new ontology-native flow.


def render(concept: Concept, bindings: Dict[str, str]) -> str:
    """Render a Concept using its emitters and the current bindings."""
    logger.debug("Rendering concept: %s", getattr(concept, 'id', 'unknown'))
    if not concept or not concept.emitters:
        # Return empty so concepts without emitters (e.g. synthetic roots for
        # executable instruction lists, or abstract nodes) contribute nothing
        # to the final output. The current emitter machinery is used as-is.
        return ""

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
                t = prod.get("type")
                ptype = (t.id if isinstance(t, Concept) else (t or "")).lower()
                ptype_leaf = ptype.rsplit("/", 1)[-1] if "/" in ptype else ptype
                rt = (required_type.id if isinstance(required_type, Concept) else required_type or "").lower()
                rt_leaf = rt.rsplit("/", 1)[-1] if "/" in rt else rt
                if ptype in (rt, "any") or ptype_leaf in (rt, rt_leaf, "any") or ptype_leaf == "any":
                    logger.debug("      %s can produce type '%s'", concept.id, required_type)
                    return True
            elif isinstance(prod, str) and prod.lower() == (required_type.id if isinstance(required_type, Concept) else required_type or "").lower():
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
            req_type_str = req_type.id if isinstance(req_type, Concept) else str(req_type or "")
            req_type_leaf = req_type_str.rsplit("/", 1)[-1] if "/" in req_type_str else req_type_str

            satisfied = False
            for prev in context + resolved:
                if can_produce(prev, req_type):
                    satisfied = True
                    break

            if not satisfied:
                candidates = ontology.find_producers_of_type(req_type)

                # Be much stricter with 'any' — only use it as a last resort
                if req_type_str == "any" or req_type_leaf == "any":
                    # Only consider very specific producers for 'any' (e.g. actual function calls or declarations)
                    candidates = [c for c in candidates if c.kind in ("BUILTIN", "SYNTACTIC_CONSTRUCT") and "Declaration" in c.id or "Call" in c.id]

                if candidates:
                    logger.debug("    Need '%s' (%s) → found %d candidate producers",
                                 need['name'], req_type_str, len(candidates))
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

    # New post-augmentation phase: interface satisfaction / compliance checking.
    # The call now returns any nodes that satisfied an interface declaring
    # executable instructions (e.g. a Recipe whose hasIngredients requirements
    # were met by available concepts in the tree, including class matches like
    # salt/pepper satisfying "spices").
    satisfied_executables = apply_interface_satisfaction(tree) or []

    # Resolve the executable instructions (now node ids in hasInstructions etc.)
    # using the generic recursive resolver driven by requires/needs + instruction lists.
    # The order of the final list comes from the order in the ontology lists
    # (requirement satisfaction provides the sequence).
    executable_steps: list[Concept] = []
    for ex in satisfied_executables:
        executable_steps.extend(resolve_dependencies(ex, ontology=get_ontology()))

    # If we resolved any executable steps (the general "follow instructions
    # once requirements satisfied" path), prefer them for emission.
    # Otherwise fall back to the classic construct dependency resolution
    # (keeps codegen working unchanged).
    if executable_steps:
        final_concepts = executable_steps
    else:
        final_concepts = resolved_concepts

    logger.info(
        "Plan built with %d starting concepts and %d resolved dependencies",
        len(initial_concepts), len(resolved_concepts)
    )
    logger.debug("_features_to_plan completed")

    return {
        "type": "ontology_driven_plan",
        "starting_concepts": [c.id for c in initial_concepts],
        "resolved_dependencies": [c.id for c in resolved_concepts],
        "all_concepts": final_concepts,
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
    solved = solve_plan(plan)
    logger.info("tree_to_solved_plan completed")
    return solved


# ------------------------------------------------------------------
# Interface satisfaction / compliance checking (new ontology feature)
# ------------------------------------------------------------------

def _normalize_requirement(req: Any) -> dict:
    """
    Turn a requirement entry (string or dict from relations) into a uniform spec:
    {"target": str, "is_class": bool, "name": optional}
    """
    if isinstance(req, str):
        return {"target": req, "is_class": False}
    if isinstance(req, dict):
        t = req.get("target") or req.get("id") or req.get("name")
        target = t.id if isinstance(t, Concept) else t
        is_class = bool(
            req.get("isClass") or req.get("is_class") or
            req.get("kind") == "CLASS" or "class" in str(req.get("type", "")).lower()
        )
        return {"target": target, "is_class": is_class, "raw": req}
    return {"target": str(req), "is_class": False}


def _get_claimed_interface_ids(candidate: Union[Concept, dict]) -> list[str]:
    """
    Extract which interfaces / classes this candidate claims to implement or be an instance of.
    Works for both Concept objects and plain dict runtime nodes.
    Looks in: parents, isA / isa, implements, and common relation forms.
    """
    ids: list[str] = []

    def _add(val):
        if isinstance(val, str):
            ids.append(val)
        elif isinstance(val, Concept):
            ids.append(val.id)
        elif isinstance(val, (list, tuple)):
            for v in val:
                _add(v)
        elif isinstance(val, dict):
            for k in ("target", "id", "name"):
                if k in val and isinstance(val[k], str):
                    ids.append(val[k])
                elif k in val and isinstance(val[k], Concept):
                    ids.append(val[k].id)

    if isinstance(candidate, Concept):
        _add(candidate.parents)
        raw = candidate.raw or {}
        for key in ("isA", "isa", "implements", "interface"):
            _add(raw.get(key))
        rels = candidate.relations or {}
        for key in ("implements", "isImplementationOf", "satisfies", "conformsTo"):
            _add(rels.get(key))
    else:
        # dict node (runtime / test data)
        _add(candidate.get("parents"))
        for key in ("isA", "isa", "implements", "interface"):
            _add(candidate.get(key))
        rels = candidate.get("relations", {}) or candidate.get("requires", {}) or {}
        for key in ("implements", "isImplementationOf", "satisfies", "conformsTo"):
            _add(rels.get(key))

    # Dedup while preserving order
    seen = set()
    unique = []
    for i in ids:
        if i and i not in seen:
            seen.add(i)
            unique.append(i)
    return unique


def _get_required_relation_names_from_interface(iface: Concept) -> list[str]:
    """
    Given an interface Concept, extract the names of the relations it requires
    instances to provide (e.g. hasIngredients, hasInstructions).
    Looks for common declaration patterns in the interface's relations.
    """
    if not iface:
        return []

    rels = iface.relations or {}
    names: list[str] = []

    # Preferred form (as shown in recipe.json example):
    # "requires": [ {"relation": "hasIngredients", ...}, {"relation": "hasInstructions"} ]
    for item in rels.get("requires", []):
        if isinstance(item, dict):
            r = item.get("relation") or item.get("name") or item.get("slot")
            if isinstance(r, str):
                names.append(r)
        elif isinstance(item, str):
            names.append(item)

    # Alternative explicit lists on the interface
    for key in ("requiredRelations", "required_relations", "requiresRelations", "requiredSlots", "slots"):
        val = rels.get(key)
        if isinstance(val, str):
            names.append(val)
        elif isinstance(val, (list, tuple)):
            for v in val:
                if isinstance(v, str):
                    names.append(v)
                elif isinstance(v, dict):
                    r = v.get("relation") or v.get("name")
                    if isinstance(r, str):
                        names.append(r)

    # As a last resort, if the interface itself has relations whose values look like
    # requirement declarations, we could infer, but we keep it explicit for now.

    # Dedup preserving order
    seen = set()
    out = []
    for n in names:
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def _collect_relation_values(candidate: Union[Concept, dict], relation_names: list[str]) -> dict:
    """
    Given a list of relation names, pull the corresponding values from the candidate
    (whether Concept or dict) and normalize them into the internal requirement format.
    """
    rels: dict = {}
    if isinstance(candidate, Concept):
        rels = candidate.relations or {}
    elif isinstance(candidate, dict):
        rels = candidate.get("relations", {}) or candidate.get("requires", {}) or {}

    out = {}
    for rname in relation_names:
        items = rels.get(rname)
        if items is None:
            continue
        if isinstance(items, (str, dict)):
            items = [items]
        if items:
            out[rname] = [_normalize_requirement(it) for it in items]
    return out


def _get_requirements_for_interface(
    candidate: Union[Concept, dict],
    ontology: Optional[Ontology] = None,
    relation_names: list[str] = None
) -> dict:
    """
    Extract the requirements the candidate must satisfy.

    If explicit `relation_names` are provided, use them directly (override).

    Otherwise, discover the interfaces the candidate claims (via parents/isA/etc.),
    read the required relation names **from those interface definitions** in the ontology,
    then collect the actual values from the candidate using those names.

    This is the key non-hardcoded path: relation names come from the interface class.
    """
    if ontology is None:
        ontology = get_ontology()

    # Explicit override takes precedence (advanced use / tests that don't want discovery)
    if relation_names:
        return _collect_relation_values(candidate, relation_names)

    # Discovery path: find interfaces from the candidate, then read required names from them.
    claimed_ids = _get_claimed_interface_ids(candidate)
    discovered_names: list[str] = []

    for iid in claimed_ids:
        iface = ontology.get(iid)
        if iface:
            discovered_names.extend(_get_required_relation_names_from_interface(iface))

    # Dedup
    seen = set()
    unique_names = []
    for n in discovered_names:
        if n not in seen:
            seen.add(n)
            unique_names.append(n)

    if unique_names:
        return _collect_relation_values(candidate, unique_names)

    # No interfaces discovered and no explicit names given → nothing to check.
    return {}


def _item_matches_requirement(
    item: Union[Concept, dict],
    req: dict,
    ontology: Ontology
) -> bool:
    """
    Does 'item' satisfy one required slot 'req'?
    Supports:
      - exact id match
      - is_a / subclass match when req['is_class'] is True
      - also checks item.get('isA') / parents on dict nodes
    """
    target = req.get("target")
    if not target:
        return False
    t = target.id if isinstance(target, Concept) else target

    # Extract id from item (works for Concept or dict)
    if isinstance(item, Concept):
        item_id = item.id
        item_parents = item.parents or []
        item_raw = item.raw or {}
    else:
        item_id = item.get("id") or item.get("word") or item.get("name")
        item_parents = item.get("parents", []) or []
        item_raw = item

    if item_id == t:
        return True

    # Direct isA on the item itself (runtime annotation or raw data)
    item_isa = None
    if isinstance(item_raw, dict):
        item_isa = item_raw.get("isA") or item_raw.get("isa")
    if item_isa == t:
        return True

    # Transitive parent / isA check via ontology
    if ontology:
        try:
            if ontology.is_a(item_id, t):
                return True
        except Exception:
            pass

        # Also try treating the item as a Concept if possible
        if isinstance(item, Concept):
            if ontology.is_a(item, t):
                return True

    # Fallback: check parents list on dict items even without ontology hit
    if t in item_parents:
        return True

    return False


def check_interface_satisfaction(
    candidate: Union[Concept, dict],
    available: list[Union[Concept, dict]],
    ontology: Optional[Ontology] = None,
    required_relations: list[str] = None,
) -> dict:
    """
    Core new function: check whether the 'available' items satisfy the
    interface requirements declared by 'candidate'.

    Relation names are **not hardcoded**. By default they are discovered from
    the interface class(es) the candidate claims (via parents / isA / implements
    on the candidate → lookup in ontology → read the interface's "requires" etc.).

    You can still pass `required_relations` explicitly to override discovery.

    If successful, the function annotates the candidate (when mutable dict) with:
        - "isA": <primary interface id, lowercased for convenience on Recipe>
        - "satisfied_interfaces": [interface ids...]

    Returns:
        {
          "satisfied": bool,
          "matched": { relation_name: [matched_items...], ... },
          "missing": [ {"relation": , "requirement": } ... ],
          "interfaces_checked": [interface ids...]
        }
    """
    if ontology is None:
        ontology = get_ontology()

    # This now does discovery from the interface class unless required_relations is given
    requirements = _get_requirements_for_interface(
        candidate, ontology=ontology, relation_names=required_relations
    )

    claimed_interfaces = _get_claimed_interface_ids(candidate)

    if not requirements:
        return {
            "satisfied": False,
            "matched": {},
            "missing": [],
            "interfaces_checked": claimed_interfaces,
            "reason": "no requirements declared on discovered interfaces"
        }

    matched: dict = {}
    missing = []

    def _requires_external_match(rel_name: str, reqs: list[dict]) -> bool:
        """
        Decide whether the values for this relation (as declared on the concrete
        candidate) must be satisfied by searching the 'available' pool.

        Decision order (all driven by data in the ontology / candidate, no
        hardcoded relation names in source code):
        1. Look up the relation declaration in the claimed interface(s) "requires"
           list. If it carries matchFromAvailable (or declarative), use that.
        2. If any concrete requirement entry carries an explicit flag, respect it.
        3. Otherwise fall back to a content heuristic on the target values.
        """
        if not reqs:
            return False

        # 1. Primary: the interface definition for this relation (e.g. hasInstructions
        #    declared with matchFromAvailable: false means "provided by the recipe itself").
        for iface_id in claimed_interfaces:
            iface = ontology.get(iface_id)
            if not iface:
                continue
            for decl in (iface.relations or {}).get("requires", []):
                if isinstance(decl, dict):
                    if decl.get("relation") == rel_name or decl.get("name") == rel_name:
                        if "matchFromAvailable" in decl:
                            return bool(decl.get("matchFromAvailable"))
                        if "match_from_available" in decl:
                            return bool(decl.get("match_from_available"))
                        if decl.get("declarative") is True:
                            return False
                        if decl.get("declarative") is False:
                            return True

        # 2. Explicit per-requirement flags from the concrete data
        for r in reqs:
            raw = r.get("raw") or r
            if isinstance(raw, dict):
                explicit = raw.get("matchFromAvailable")
                if explicit is None:
                    explicit = raw.get("match_from_available")
                if explicit is not None:
                    return bool(explicit)

                if raw.get("declarative") is True:
                    return False
                if raw.get("declarative") is False:
                    return True

        # 3. Content heuristic (no name hardcoding)
        for r in reqs:
            raw_t = r.get("target")
            tgt = (raw_t.id if isinstance(raw_t, Concept) else raw_t) or ""
            tgt = str(tgt).strip()
            if not tgt:
                continue
            if " " in tgt or any(p in tgt for p in ".!?") or len(tgt) > 35:
                return False
            if tgt.replace("-", "").replace("_", "").replace(".", "").isalnum():
                return True

        return True  # conservative default

    for rel_name, reqs in requirements.items():
        matched[rel_name] = []

        if not _requires_external_match(rel_name, reqs):
            # Declarative part of the interface (e.g. hasInstructions) — satisfied by definition
            matched[rel_name] = [(r.get("target").id if isinstance(r.get("target"), Concept) else r.get("target")) for r in reqs]
            continue

        for req in reqs:
            found = None
            for item in available:
                if _item_matches_requirement(item, req, ontology):
                    found = item
                    break
            if found is not None:
                matched[rel_name].append(found)
            else:
                missing.append({"relation": rel_name, "requirement": req})

    satisfied = len(missing) == 0

    result = {
        "satisfied": satisfied,
        "matched": matched,
        "missing": missing,
        "interfaces_checked": claimed_interfaces,
    }

    if satisfied and isinstance(candidate, dict):
        # Dynamic annotation based on the actual interfaces we are satisfying
        for iface_id in claimed_interfaces:
            candidate.setdefault("satisfied_interfaces", []).append(iface_id)
            # Convenience for the common Recipe case (and similar)
            if iface_id.lower() in ("recipe", "recipes"):
                candidate["isA"] = "recipe"

        # If nothing was claimed but we still satisfied something (explicit relations mode),
        # fall back to a generic marker so callers/tests have something.
        if not claimed_interfaces:
            candidate.setdefault("satisfied_interfaces", []).append("satisfied")
            # Only set the old "recipe" convenience if the keys look recipe-like
            if any(k in requirements for k in ("hasIngredients", "hasInstructions")):
                candidate["isA"] = "recipe"

    return result


def apply_interface_satisfaction(
    tree,
    extra_available: Optional[list] = None,
    ontology: Optional[Ontology] = None,
):
    """
    Post-augmentation hook.

    After add_concepts + dependency resolution, this walks the concepts
    attached to the tree (plus any caller-supplied extra_available nodes)
    and runs interface satisfaction checks.

    Interface discovery and required relation names come from the ontology
    classes the candidates claim (parents / isA / implements), not from
    hardcoded lists in this module.

    Returns the list of nodes (Concept or dict) that successfully satisfied
    an interface which declares executable content (e.g. hasInstructions).
    The caller can then pass these to resolve_dependencies to obtain the
    ordered list of instruction nodes to emit.
    """
    if ontology is None:
        ontology = get_ontology()

    pool: list = list(extra_available) if extra_available else []

    # Collect everything already attached to the tree
    for leaf in _walk_leaves(tree):
        for c in leaf.get("concepts", []):
            if isinstance(c, Concept):
                pool.append(c)
        # Also include the leaf itself as a potential runtime node
        pool.append(leaf)

    # Now look for candidates that declare interface-style requirements
    # We scan both attached concepts and any rich dict nodes
    seen_candidates = set()
    satisfied_executables: list = []

    def check_one(obj):
        key = id(obj)
        if key in seen_candidates:
            return
        seen_candidates.add(key)

        # Discovery is driven by the interfaces the obj claims (parents/isA/etc.)
        # No hardcoded relation names here.
        reqs = _get_requirements_for_interface(obj, ontology=ontology)
        if not reqs:
            return

        result = check_interface_satisfaction(obj, pool, ontology=ontology)
        if result.get("satisfied"):
            # Does this satisfied node declare executable instructions/steps?
            # (generic: look for hasInstructions or similar; the concrete values
            # are node ids of action concepts that have emitters)
            has_exec_list = False
            if isinstance(obj, Concept):
                has_exec_list = bool((obj.relations or {}).get("hasInstructions"))
            elif isinstance(obj, dict):
                rels = obj.get("relations", {}) or obj.get("requires", {}) or {}
                has_exec_list = bool(rels.get("hasInstructions"))
            if has_exec_list:
                satisfied_executables.append(obj)

    # Check attached concepts
    for leaf in _walk_leaves(tree):
        for c in leaf.get("concepts", []):
            if isinstance(c, Concept):
                check_one(c)

        # Also check the leaf dict itself (it may carry runtime relations)
        if isinstance(leaf, dict) and _get_requirements_for_interface(leaf, ontology=ontology):
            check_one(leaf)

    # Also give extra_available items a chance (they may be the ones declaring the contract)
    for item in (extra_available or []):
        check_one(item)

    logger.debug("apply_interface_satisfaction completed")
    return satisfied_executables


def resolve_dependencies(
    node: Union[Concept, dict, str, list],
    ontology: Optional[Ontology] = None,
    visited: Optional[set] = None,
) -> list[Concept]:
    """
    Generic recursive resolver for executable content unlocked by requirement satisfaction.

    It reads a node's requires/needs fields (and executable instruction lists such as
    hasInstructions) and calls itself recursively. The order of the returned list
    follows the order of the lists in the ontology (the "requirement satisfaction" order).

    - If a node id appears in hasInstructions (or steps/procedure), those nodes are
      resolved in that sequence.
    - Standard needs/requires are also followed (so an action could declare further
      sub-requirements that get resolved before it).
    - A node is appended to the result only if it has emitters (i.e. it is directly
      renderable via the existing emitter). This keeps the mechanism shallow and
      lets the current render/emit do the actual output work.

    This is deliberately generic: Recipe + hasInstructions is only the motivating
    example. Any interface can declare relations whose values are node ids that
    become executable once the interface requirements are satisfied.
    """
    if ontology is None:
        ontology = get_ontology()

    if visited is None:
        visited = set()

    # Handle list of starting points (order preserved)
    if isinstance(node, list):
        results: list[Concept] = []
        for n in node:
            results.extend(resolve_dependencies(n, ontology, visited))
        return results

    # Resolve string id to Concept
    if isinstance(node, str):
        c = ontology.get(node)
        if not c:
            return []
        node = c

    # Support lightweight dict nodes that carry an id (runtime leaves etc.)
    if isinstance(node, dict):
        nid = node.get("id")
        if nid:
            c = ontology.get(nid)
            if c:
                node = c
            else:
                # Shallow: if the dict itself carries an emitter we could synthesize,
                # but for now we expect real registered Concepts for actions.
                return []
        else:
            return []

    if not isinstance(node, Concept):
        return []

    if node.id in visited:
        return []
    visited.add(node.id)

    results: list[Concept] = []
    rels = node.relations or {}

    # Follow standard requires / needs first (dependencies before the step)
    for field in ("needs", "requires", "hasParameter"):
        items = rels.get(field, [])
        if isinstance(items, (str, dict)):
            items = [items]
        for item in items:
            target = None
            if isinstance(item, Concept):
                target = item
            elif isinstance(item, str):
                target = item
            elif isinstance(item, dict):
                t = item.get("target") or item.get("id")
                target = t if isinstance(t, (str, Concept)) else None
            if target:
                results.extend(resolve_dependencies(target, ontology, visited))

    # Follow *whatever relations the claimed interfaces declare in their "requires"*
    # (generic, driven by the interface class definition, not hardcoded field names here).
    # This discovers hasInstructions (the executable steps) etc. from the interface
    # (e.g. Recipe). The values (node ids) get resolved recursively in list order.
    claimed = _get_claimed_interface_ids(node)
    for iface_id in claimed:
        iface = ontology.get(iface_id)
        if not iface:
            continue
        for decl in (iface.relations or {}).get("requires", []):
            if isinstance(decl, dict):
                rname = decl.get("relation") or decl.get("name")
                if rname:
                    items = rels.get(rname, [])
                    if isinstance(items, (str, dict)):
                        items = [items]
                    for item in items:
                        target = None
                        if isinstance(item, Concept):
                            target = item
                        elif isinstance(item, str):
                            target = item
                        elif isinstance(item, dict):
                            t = item.get("target") or item.get("id") or item.get("action")
                            target = t if isinstance(t, (str, Concept)) else None
                        if target:
                            results.extend(resolve_dependencies(target, ontology, visited))

    # If this node itself is directly executable (carries emitters), include it
    # so the normal render/emit will produce its output line.
    # Action nodes (the leaves in the instruction lists) will be included here.
    # High-level nodes like "fried_egg" usually won't have emitters, so they
    # contribute only their expanded instruction steps.
    if getattr(node, "emitters", None):
        results.append(node)

    return results
