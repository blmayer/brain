"""Natural language → KB annotation → needs satisfaction → emission.

Public API (four steps):
  parse(sentence)  → constituency tree (pronouns resolved)
  augment(tree)    → same tree with KB Concepts attached to leaves
  solve(tree)      → ExecNode graph with needs satisfied from the pool / KB
  emit(graph)      → output lines from emitter templates
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

import nltk

from kb import Concept, get_ontology
from logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class ExecNode:
    """A concept in the solved graph, with role bindings and child dependencies."""
    concept: Concept
    bindings: Dict[str, str] = field(default_factory=dict)
    deps: List["ExecNode"] = field(default_factory=list)


_STOP_MATCH_WORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "am", "do", "does", "did", "to", "of", "in", "on", "for", "and", "or",
    "but", "with", "as", "by", "at", "from", "that", "this", "it", "its",
})


def _leaf_dict(leaf: Any) -> dict:
    if isinstance(leaf, dict):
        return leaf
    if isinstance(leaf, (list, tuple)) and len(leaf) >= 2:
        return {"word": str(leaf[0]), "pos": str(leaf[1]), "reference": None}
    return {"word": str(leaf), "pos": "UNK", "reference": None}


def _walk_leaves(tree: Any):
    if tree is None:
        return
    if isinstance(tree, dict):
        yield tree
        return
    if isinstance(tree, (list, tuple)) and not isinstance(tree, nltk.Tree):
        for item in tree:
            yield from _walk_leaves(item)
        return
    try:
        for raw in tree.leaves():
            yield _leaf_dict(raw)
    except Exception:
        for child in getattr(tree, "children", []) or []:
            yield from _walk_leaves(child)


def _display_name(concept: Union[Concept, str, None]) -> str:
    if concept is None:
        return ""
    if isinstance(concept, str):
        s = concept.strip()
        if not s:
            return ""
        if "/" in s:
            return s.rsplit("/", 1)[-1].replace("_", " ").lower()
        return s.lower()
    name = (getattr(concept, "name", None) or "").strip()
    if name:
        return name.lower()
    cid = getattr(concept, "id", "") or ""
    return cid.rsplit("/", 1)[-1].replace("_", " ").lower()


def _as_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _target_concept(entry: Any) -> Optional[Concept]:
    ontology = get_ontology()
    if isinstance(entry, Concept):
        return entry
    if isinstance(entry, dict):
        t = entry.get("target") or entry.get("id")
        if isinstance(t, Concept):
            return t
        if isinstance(t, str):
            return ontology.get(t)
    if isinstance(entry, str):
        return ontology.get(entry)
    return None


def _relation_entries(concept: Concept, *names: str) -> list:
    rels = concept.relations or {}
    out: list = []
    for name in names:
        out.extend(_as_list(rels.get(name)))
    return out


def _needs_of(concept: Concept) -> List[dict]:
    needs: List[dict] = []
    for item in _relation_entries(concept, "needs", "hasParameter"):
        if isinstance(item, dict):
            needs.append({
                "name": item.get("name") or item.get("slot") or "arg",
                "type": item.get("type") or "any",
                "raw": item,
            })
        elif isinstance(item, Concept):
            needs.append({"name": item.id, "type": item, "raw": item})
        elif isinstance(item, str):
            needs.append({"name": item, "type": item, "raw": item})
    return needs


def _type_key(t: Any) -> str:
    if isinstance(t, Concept):
        return (t.id or t.kind or "").lower()
    if t is None:
        return "any"
    return str(t).strip().lower()


def _type_leaf(t: Any) -> str:
    k = _type_key(t)
    return k.rsplit("/", 1)[-1] if "/" in k else k


def _concept_matches_need_type(concept: Concept, need_type: Any) -> bool:
    if need_type is None or _type_key(need_type) in ("", "any"):
        return True
    nt = _type_key(need_type)
    nl = _type_leaf(need_type)
    kind = (getattr(concept, "kind", "") or "").lower()
    cid = (getattr(concept, "id", "") or "").lower()
    if kind == nt or kind == nl:
        return True
    if cid == nt or cid.endswith("/" + nl) or cid.rsplit("/", 1)[-1] == nl:
        return True
    ontology = get_ontology()
    try:
        if ontology.is_a(concept, nt) or ontology.is_a(concept, nl):
            return True
    except Exception:
        pass
    for prod in _relation_entries(concept, "produces"):
        if isinstance(prod, dict):
            pt = prod.get("type")
            if pt is None:
                continue
            pk = _type_key(pt)
            pl = _type_leaf(pt)
            if pk in (nt, nl) or pl in (nt, nl) or pk == "any" or pl == "any":
                return True
        elif isinstance(prod, Concept) and (
            prod.id.lower() in (nt, nl) or (prod.kind or "").lower() in (nt, nl)
        ):
            return True
        elif isinstance(prod, str) and prod.lower() in (nt, nl):
            return True
    return False


def _verb_expresses_map() -> Dict[str, Concept]:
    mapping: Dict[str, Concept] = {}
    for c in get_ontology().concepts.values():
        if getattr(c, "kind", "") != "VERB":
            continue
        for e in _as_list((c.relations or {}).get("expresses")):
            key = e if isinstance(e, str) else getattr(e, "id", None)
            if isinstance(key, str) and key and key not in mapping:
                mapping[key] = c
    return mapping


def _render(concept: Concept, bindings: Dict[str, str]) -> str:
    if not concept or not concept.emitters:
        return ""
    template = concept.emitters[0].get("template", "") or ""
    return re.sub(
        r"\{\{([^}]+)\}\}",
        lambda m: str(bindings.get(m.group(1).strip(), m.group(1).strip())),
        template,
    )


def _emit_order(concept: Concept) -> int:
    for entry in _relation_entries(concept, "emitOrder", "emit_order"):
        if isinstance(entry, (int, float)):
            return int(entry)
        if isinstance(entry, dict) and "value" in entry:
            try:
                return int(entry["value"])
            except (TypeError, ValueError):
                pass
        if isinstance(entry, str) and entry.strip().lstrip("-").isdigit():
            return int(entry.strip())
    return 0


def _word_intentionally_matches(concept: Concept, word: str) -> bool:
    w = (word or "").lower().strip()
    if not w or not concept:
        return False
    for kw in concept.keywords or []:
        kl = kw.lower().strip()
        if w == kl or w in kl.split() or kl in w.split():
            return True
    name = (concept.name or "").lower().strip()
    if name and (w == name or w in name.split()):
        return True
    leaf = (concept.id or "").rsplit("/", 1)[-1].lower().replace("_", " ")
    if w == leaf or w == leaf.replace(" ", "") or w in leaf.split():
        return True
    cid = (concept.id or "").lower()
    if cid == w or cid.endswith("/" + w):
        return True
    return False


def _seed_concepts(tree) -> List[Concept]:
    seen: set = set()
    out: List[Concept] = []
    for leaf in _walk_leaves(tree):
        for c in leaf.get("concepts") or []:
            if isinstance(c, Concept) and c.id not in seen:
                seen.add(c.id)
                out.append(c)
    return out


def _has_parts_ids(root: Concept) -> set:
    ids: set = set()
    for entry in _relation_entries(root, "hasParts", "has_parts"):
        tgt = _target_concept(entry)
        if tgt is not None:
            ids.add(tgt.id)
        elif isinstance(entry, str):
            ids.add(entry)
    return ids


def _scope_roots(seeds: List[Concept]) -> List[Concept]:
    roots = [c for c in seeds if _relation_entries(c, "hasParts", "has_parts")]
    if not roots:
        return []

    def _parts_under_prefix(root: Concept) -> bool:
        rid = root.id or ""
        parts = _has_parts_ids(root)
        if not parts:
            return True
        return all(p == rid or p.startswith(rid + "/") for p in parts)

    prefix_roots = [r for r in roots if _parts_under_prefix(r)]
    return prefix_roots if prefix_roots else roots


def _under_scope(concept: Concept, root: Concept) -> bool:
    if concept.id == root.id:
        return True
    rid = root.id or ""
    if (concept.id or "").startswith(rid + "/"):
        return True
    if concept.id in _has_parts_ids(root):
        return True
    for entry in _relation_entries(concept, "partOf", "part_of"):
        tgt = _target_concept(entry)
        if tgt is not None and (tgt.id == rid or (tgt.id or "").startswith(rid + "/")):
            return True
        if isinstance(entry, str) and (entry == rid or entry.startswith(rid + "/")):
            return True
    return False


def parse(sentence: str):
    from parsers import get_default_parser
    logger.info("parse: %r", sentence)
    resolved_tree, _raw = get_default_parser().parse(sentence)
    return resolved_tree


def augment(tree):
    ontology = get_ontology()

    def attach(leaf: dict, word: str, pos: str = "") -> None:
        if not isinstance(word, str) or not word.strip():
            leaf["concepts"] = []
            return
        wlow = word.lower().strip()
        pos_u = (pos or leaf.get("pos") or "").upper()
        if wlow in _STOP_MATCH_WORDS and not pos_u.startswith(("WP", "WRB", "WDT")):
            leaf["concepts"] = []
            return
        matches = ontology.find_concepts_matching(wlow, strict=True)
        matches = [c for c in (matches or []) if _word_intentionally_matches(c, wlow)]
        leaf["concepts"] = matches
        if matches:
            logger.debug("augment leaf %r → %s", word, [c.id for c in matches])

    def process(node: Any) -> None:
        if node is None:
            return
        if isinstance(node, dict):
            attach(node, node.get("word", ""), node.get("pos", ""))
            return
        if isinstance(node, nltk.Tree):
            for i in range(len(node)):
                child = node[i]
                if isinstance(child, nltk.Tree):
                    process(child)
                elif isinstance(child, dict):
                    attach(child, child.get("word", ""), child.get("pos", ""))
                elif isinstance(child, (list, tuple)) and len(child) >= 2:
                    word, pos = str(child[0]), str(child[1])
                    node[i] = {
                        "word": word, "pos": pos, "reference": None, "concepts": [],
                    }
                    attach(node[i], word, pos)
                else:
                    w = str(child)
                    node[i] = {
                        "word": w, "pos": "UNK", "reference": None, "concepts": [],
                    }
                    attach(node[i], w)
            return
        if isinstance(node, (list, tuple)):
            for item in node:
                process(item)

    process(tree)
    logger.info("augment: attached concepts %s", [c.id for c in _seed_concepts(tree)])
    return tree


def solve(tree) -> ExecNode:
    ontology = get_ontology()
    seeds = _seed_concepts(tree)

    scopes = _scope_roots(seeds)
    if scopes:
        scope = scopes[0]
        for s in seeds:
            if s in scopes:
                scope = s
                break
        seeds = [c for c in seeds if _under_scope(c, scope)]
        if scope not in seeds:
            seeds = [scope] + seeds
        logger.info("solve: scoped to %s", scope.id)

    logger.info("solve: seeds=%s", [c.id for c in seeds])
    seed_ids = {c.id for c in seeds}
    by_id: Dict[str, Concept] = {c.id: c for c in seeds}

    changed = True
    while changed:
        changed = False
        for concept in list(by_id.values()):
            for prod in _relation_entries(concept, "produces"):
                tgt = _target_concept(prod)
                if tgt is not None and tgt.id not in by_id:
                    by_id[tgt.id] = tgt
                    changed = True
            for hp in _relation_entries(concept, "hasParent", "has_parent"):
                tgt = _target_concept(hp)
                if (
                    tgt is not None
                    and tgt.id not in by_id
                    and (tgt.emitters or _needs_of(tgt))
                ):
                    by_id[tgt.id] = tgt
                    changed = True

    expresses = _verb_expresses_map()
    for concept in list(by_id.values()):
        if getattr(concept, "kind", "") != "FACT":
            continue
        for rel_key, rel_val in (concept.relations or {}).items():
            verb = expresses.get(rel_key)
            if verb is None:
                continue
            if verb.id not in by_id:
                by_id[verb.id] = verb
            for entry in _as_list(rel_val):
                tgt = _target_concept(entry)
                if tgt is not None and tgt.id not in by_id:
                    by_id[tgt.id] = tgt

    pool = list(by_id.values())
    kind_like = frozenset({
        "fact", "verb", "class", "answer_type", "interrogative",
        "english_construct", "interface", "recipe",
    })
    nodes: Dict[str, ExecNode] = {c.id: ExecNode(concept=c) for c in pool}

    for concept in pool:
        node = nodes[concept.id]
        used_ids: set = set()
        for need in _needs_of(concept):
            name = need["name"]
            if name in node.bindings:
                continue
            ntype = need["type"]
            nleaf = _type_leaf(ntype)
            filler: Optional[Concept] = None
            for cand in pool:
                if cand.id == concept.id or cand.id in used_ids:
                    continue
                if _concept_matches_need_type(cand, ntype):
                    filler = cand
                    break
            if filler is None and nleaf not in kind_like and _type_key(ntype) not in ("", "any"):
                for cand in ontology.find_producers_of_type(ntype):
                    if cand.id in used_ids:
                        continue
                    if cand.id not in by_id:
                        by_id[cand.id] = cand
                        nodes[cand.id] = ExecNode(concept=cand)
                        pool.append(cand)
                        filler = cand
                        break
                    filler = by_id[cand.id]
                    break
            if filler is not None:
                node.bindings[name] = _display_name(filler)
                used_ids.add(filler.id)
                if name == "subject" and getattr(filler, "kind", "") == "FACT":
                    _bind_from_fact_edge(node, filler, pool, expresses)

        if concept.emitters and _needs_of(concept) and not node.bindings.get("subject"):
            need_names = {n["name"] for n in _needs_of(concept)}
            if need_names & {"subject", "verb", "object"}:
                _bind_answer_roles(node, pool, expresses)

    produced_ids = set()
    for s in seeds:
        for prod in _relation_entries(s, "produces"):
            tgt = _target_concept(prod)
            if tgt is not None:
                produced_ids.add(tgt.id)

    def _is_emit_target(c: Concept) -> bool:
        if not c.emitters:
            return False
        if c.id in seed_ids:
            return True
        if c.id in produced_ids:
            return True
        if _needs_of(c) and c.emitters:
            return c.id in by_id and any(
                n["name"] in ("subject", "verb", "object") for n in _needs_of(c)
            )
        return False

    organizers = [
        nodes[c.id] for c in pool if c.id in nodes and _is_emit_target(c)
    ]
    seed_index = {c.id: i for i, c in enumerate(seeds)}

    def sort_key(n: ExecNode):
        return (
            _emit_order(n.concept),
            seed_index.get(n.concept.id, 10_000),
            n.concept.id,
        )

    organizers = sorted(organizers, key=sort_key)
    root = ExecNode(
        concept=Concept(id="ExecutionList", kind="EXEC", name="Execution List"),
        deps=list(organizers),
    )
    seen_ids = {d.concept.id for d in root.deps}
    for c in seeds:
        if c.id in nodes and c.id not in seen_ids and not c.emitters:
            root.deps.append(nodes[c.id])
            seen_ids.add(c.id)

    logger.info(
        "solve: pool=%s emit_candidates=%s",
        [c.id for c in pool],
        [d.concept.id for d in root.deps if d.concept.emitters],
    )
    return root


def _bind_from_fact_edge(node, fact, pool, expresses):
    verb_ids = {c.id for c in pool if getattr(c, "kind", "") == "VERB"}
    for rel_key, rel_val in (fact.relations or {}).items():
        verb = expresses.get(rel_key)
        if verb is None or verb.id not in verb_ids:
            continue
        node.bindings.setdefault("verb", _display_name(verb))
        for entry in _as_list(rel_val):
            obj = _target_concept(entry)
            if obj is not None:
                node.bindings.setdefault("object", _display_name(obj))
                return
            if isinstance(entry, str) and entry.strip() and "/" not in entry:
                node.bindings.setdefault("object", entry.strip().lower())
                return


def _bind_answer_roles(node, pool, expresses):
    facts = [
        c for c in pool
        if getattr(c, "kind", "") == "FACT"
        and not (c.id or "").startswith("linguistics/")
    ]
    verbs = [c for c in pool if getattr(c, "kind", "") == "VERB"]
    verb_to_keys: Dict[str, List[str]] = {}
    for rel_key, verb in expresses.items():
        verb_to_keys.setdefault(verb.id, []).append(rel_key)
    for verb in verbs:
        for fact in facts:
            for key in verb_to_keys.get(verb.id, []):
                if key not in (fact.relations or {}):
                    continue
                node.bindings["subject"] = _display_name(fact)
                node.bindings["verb"] = _display_name(verb)
                for entry in _as_list(fact.relations.get(key)):
                    obj = _target_concept(entry)
                    if obj is not None:
                        node.bindings["object"] = _display_name(obj)
                        return
                    if isinstance(entry, str) and entry.strip() and "/" not in entry:
                        node.bindings["object"] = entry.strip().lower()
                        return
                return
    if facts:
        node.bindings.setdefault("subject", _display_name(facts[0]))
    if verbs:
        node.bindings.setdefault("verb", _display_name(verbs[0]))
    if len(facts) > 1:
        node.bindings.setdefault("object", _display_name(facts[1]))


def emit(graph, visited=None, out=None):
    if visited is None:
        visited = {}
        logger.info(
            "emit from root=%s deps=%s",
            getattr(graph.concept, "id", "?"),
            [getattr(d.concept, "id", "?") for d in (graph.deps or [])],
        )
    if out is None:
        out = []
    key = (getattr(graph.concept, "id", "?") or "?") + str(id(graph))
    if visited.get(key):
        return out
    visited[key] = True
    for d in graph.deps or []:
        emit(d, visited, out)
    line = _render(graph.concept, graph.bindings)
    if line and "{{" not in line:
        logger.info("emit line from %s: %s", graph.concept.id, line)
        out.append(line)
    return out
