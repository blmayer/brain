"""Knowledge Base — Ontology First

We now use the new Golang ontology format exclusively.
"""

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any, Optional, Union

from logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class Concept:
    """A concept loaded from the KB JSON files (under kb/programming_languages/)."""
    id: str
    kind: str
    name: str
    parents: List[str] = field(default_factory=list)
    relations: Dict[str, Any] = field(default_factory=dict)
    emitters: List[Dict[str, Any]] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)   # indicator / trigger words
    raw: Dict[str, Any] = field(default_factory=dict)


class Ontology:
    """The main knowledge container for the project."""

    def __init__(self):
        self.concepts: Dict[str, Concept] = {}
        self.loaded_paths: List[Path] = []

    def register(self, concept: Concept):
        self.concepts[concept.id] = concept

    def get(self, concept_id: str) -> Optional[Concept]:
        return self.concepts.get(concept_id)

    def find_concepts_matching(self, keywords: list[str] | str, strict: bool = True) -> list[Concept]:
        """
        Find concepts that match any of the given keywords.

        Results are sorted by relevance (number of keyword matches, descending).
        This allows callers to take the best match(es) instead of an arbitrary order.

        When strict=True (recommended):
        - Matches primarily against id, name, and the 'keywords' field.
        When strict=False:
        - Also searches description, parents, relations, etc.
        """
        logger.debug("find_concepts_matching called with keywords: %s (strict=%s)", keywords, strict)

        if isinstance(keywords, str):
            keywords = [keywords]

        keywords = [k.lower().strip() for k in keywords if k.strip()]
        if not keywords:
            return []

        scored_results = []   # list of (concept, match_count)

        def _word_match(haystack: str, needle: str) -> bool:
            if not needle:
                return False
            h = haystack.lower()
            n = needle.lower()
            if n in h.split():
                return True
            # word boundary (handles punctuation and paths like .../program/...)
            if re.search(r'(?i)\b' + re.escape(n) + r'\b', h):
                return True
            # also allow match on the leaf of a path id (e.g. word "declaration" matches .../declaration)
            leaf = h.rsplit("/", 1)[-1]
            if n == leaf or n in leaf.split("_"):
                return True
            return False

        for concept in self.concepts.values():
            # Build the text we will search in
            if strict:
                searchable = " ".join([
                    concept.id.lower(),
                    concept.name.lower(),
                ])
                if concept.keywords:
                    searchable += " " + " ".join(kw.lower() for kw in concept.keywords)
            else:
                # Broader search
                parts = [
                    concept.id.lower(),
                    concept.name.lower(),
                    " ".join([p.id if isinstance(p, Concept) else str(p) for p in (concept.parents or [])]).lower(),
                    str(concept.relations).lower(),
                    str(concept.emitters).lower(),
                ]
                if isinstance(concept.raw, dict):
                    desc = concept.raw.get("description", "")
                    if desc:
                        parts.append(desc.lower())
                if concept.keywords:
                    parts.extend(kw.lower() for kw in concept.keywords)
                searchable = " ".join(parts)

            # Count how many of the input keywords appear (whole-word / leaf aware)
            match_count = sum(1 for kw in keywords if _word_match(searchable, kw))

            if match_count > 0:
                scored_results.append((concept, match_count))

        # Sort by number of matches (descending), then by name for stability
        scored_results.sort(key=lambda x: (-x[1], x[0].name.lower()))

        # Return only the concepts (the caller can take the first one or the whole ranked list)
        return [concept for concept, score in scored_results]

    def find_related_concepts(self, concept: Concept, relation_names: list[str] = None) -> list[Concept]:
        """
        Given a concept, follow its relations to find other concepts it depends on or is related to.
        Example: for a "print" concept, find the actual "fmt.Println" implementation concept.
        """
        logger.debug("find_related_concepts called on %s", concept.id)
        if relation_names is None:
            relation_names = ["needs", "hasParameter", "importsPackage", "relatedTo", "implementedBy"]

        related = []
        rels = concept.relations or {}

        for rel_name in relation_names:
            targets = rels.get(rel_name, [])
            if isinstance(targets, dict):
                targets = [targets]

            for target in targets:
                if isinstance(target, Concept):
                    related.append(target)
                elif isinstance(target, dict):
                    t = target.get("target") or target.get("id")
                    if isinstance(t, Concept):
                        related.append(t)
                    elif isinstance(t, str) and t in self.concepts:
                        related.append(self.concepts[t])
                elif isinstance(target, str) and target in self.concepts:
                    related.append(self.concepts[target])

        return related

    def find_producers_of_type(self, target_type: str) -> list[Concept]:
        """
        Find concepts in the ontology that can produce a value/binding of the given type.
        Used for proper dependency satisfaction.
        """
        if isinstance(target_type, Concept):
            target_type = target_type.id
        logger.debug("find_producers_of_type called for type: %s", target_type)
        producers = []
        target_type = target_type.lower()
        target_type_leaf = target_type.rsplit("/", 1)[-1] if "/" in target_type else target_type

        for concept in self.concepts.values():
            rels = concept.relations or {}

            for prod in rels.get("produces", []):
                if isinstance(prod, dict):
                    t = prod.get("type")
                    ptype = (t.id if isinstance(t, Concept) else (t or "")).lower()
                    ptype_leaf = ptype.rsplit("/", 1)[-1] if "/" in ptype else ptype
                    tt = target_type
                    if ptype == tt or ptype_leaf == tt or ptype == target_type_leaf or ptype_leaf == target_type_leaf or ptype == "any" or ptype_leaf == "any":
                        producers.append(concept)
                        break
                elif isinstance(prod, str) and prod.lower() == target_type:
                    producers.append(concept)
                    break

            raw_str = str(concept.raw).lower()
            if (target_type in raw_str or target_type_leaf in raw_str) and "return" in raw_str:
                if concept not in producers:
                    producers.append(concept)

        return producers

    def find_implementations_of(self, concept_id: str) -> list[Concept]:
        """
        Given a concept id (e.g. "PrintOperation"), return all concepts that
        specialize or implement it (e.g. "fmt.Println").
        """
        logger.debug("find_implementations_of called for: %s", concept_id)
        implementations = []
        target = self.get(concept_id)
        if not target:
            return implementations

        for concept in self.concepts.values():
            rels = concept.relations or {}
            for rel_name in ["specializes", "implements", "isImplementationOf"]:
                targets = rels.get(rel_name, [])
                if isinstance(targets, (str, dict)):
                    targets = [targets]
                for t in targets:
                    if isinstance(t, Concept):
                        tid = t.id
                    elif isinstance(t, dict):
                        tt = t.get("target") or t.get("id")
                        tid = tt.id if isinstance(tt, Concept) else tt
                    else:
                        tid = t
                    if tid == concept_id:
                        implementations.append(concept)
                        break

        return implementations

    def get_ancestors(self, concept_id: str, max_depth: int = 20) -> set[str]:
        """
        Return all ancestor concept ids (transitive parents) for the given id.
        Includes the concept itself.
        """
        visited: set[str] = set()
        to_visit: list[str] = [concept_id]
        depth = 0

        while to_visit and depth < max_depth:
            current = to_visit.pop()
            if current in visited:
                continue
            visited.add(current)

            c = self.get(current)
            if not c:
                continue

            parents = c.parents or []
            if isinstance(c.raw, dict):
                # Support explicit isA as well as parents list
                explicit = c.raw.get("isA")
                if isinstance(explicit, str):
                    parents = parents + [explicit]
                elif isinstance(explicit, list):
                    parents = parents + explicit

            for p in parents:
                if isinstance(p, str) and p not in visited:
                    to_visit.append(p)
                elif isinstance(p, Concept):
                    pid = p.id
                    if pid not in visited:
                        to_visit.append(pid)
            depth += 1

        return visited

    def is_a(self, concrete: Union[str, "Concept"], abstract: str) -> bool:
        """
        Structural/nominal 'is a' check with transitive parents.

        concrete can be a concept id or a Concept object.
        Returns True if concrete is the same as abstract or abstract is among its ancestors.
        """
        if isinstance(concrete, Concept):
            cid = concrete.id
        else:
            cid = str(concrete)

        if cid == abstract:
            return True

        ancestors = self.get_ancestors(cid)
        return abstract in ancestors

    def load_from_directory(self, base_path: Path):
        if not base_path.exists():
            return

        for json_file in base_path.rglob("*.json"):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    text = f.read().strip()

                # Robust parse: tolerate trailing garbage (e.g. shell artifacts
                # like "EOF 2>&1" that appear in some legacy kb/*.json files).
                try:
                    data = json.loads(text)
                except json.JSONDecodeError:
                    decoder = json.JSONDecoder()
                    data, _ = decoder.raw_decode(text)

                if isinstance(data, list):
                    for item in data:
                        self._load_single_concept(item, json_file)
                elif isinstance(data, dict) and "instances" in data:
                    for item in data["instances"]:
                        self._load_single_concept(item, json_file)
                else:
                    self._load_single_concept(data, json_file)

                self.loaded_paths.append(json_file)
            except Exception as e:
                print(f"[Ontology] Failed to load {json_file}: {e}")

        # After all files loaded, turn string id refs into direct Concept pointers
        # so relations/parents contain real nodes (graph edges) not just ids.
        self._resolve_links()

    def _load_single_concept(self, data: Dict, source: Path):
        if not isinstance(data, dict):
            return

        # Support legacy triplet/definition style files that don't have a top-level "id"
        # but have "subject" + "definitions". Turn the subject into an id so that
        # get_ontology() truly ingests everything under kb/.
        if "id" not in data and "subject" in data:
            data = dict(data)  # don't mutate original
            data["id"] = data["subject"]
            if "kind" not in data:
                data["kind"] = "FACT"
            if "name" not in data:
                data["name"] = data["subject"]
            # Put the definitions into relations/raw for later use
            if "definitions" in data and "relations" not in data:
                data.setdefault("relations", {})["definitions"] = data["definitions"]

        if "id" not in data:
            return

        parents = data.get("parents", []) or []
        # Support "is_a" / "isA" (shallow for now, as alias for interface / kind membership)
        for k in ("is_a", "isA", "isa"):
            val = data.get(k)
            if val:
                if isinstance(val, str):
                    if val not in parents:
                        parents = list(parents) + [val]
                elif isinstance(val, (list, tuple)):
                    for v in val:
                        if isinstance(v, str) and v not in parents:
                            parents = list(parents) + [v]

        concept = Concept(
            id=data["id"],
            kind=data.get("kind", "UNKNOWN"),
            name=data.get("name", data["id"]),
            parents=parents,
            relations=data.get("relations", {}),
            emitters=data.get("emitters", []),
            keywords=data.get("keywords", []),
            raw=data,
        )
        self.register(concept)

    def __len__(self):
        return len(self.concepts)

    def _resolve_links(self):
        """Post-load: substitute string node ids inside parents and relations
        with direct Concept object references (in-memory 'pointers').
        Virtual/undefined ids (e.g. abstract 'Statement') remain as strings.
        raw/ is left untouched (original source strings).
        """
        for concept in list(self.concepts.values()):
            # parents may mix str (virtual) and Concept now
            new_parents: list = []
            for p in (concept.parents or []):
                if isinstance(p, str):
                    c = self.concepts.get(p)
                    new_parents.append(c if c is not None else p)
                else:
                    new_parents.append(p)
            concept.parents = new_parents

            concept.relations = self._dereference_val(concept.relations or {})

    def _dereference_val(self, val: Any) -> Any:
        """Recursively replace any str that is a known concept id with the Concept."""
        if isinstance(val, str):
            c = self.concepts.get(val)
            return c if c is not None else val
        if isinstance(val, list):
            return [self._dereference_val(x) for x in val]
        if isinstance(val, dict):
            d = dict(val)
            for lk in ("target", "id", "concept", "type"):
                if lk in d and isinstance(d[lk], str):
                    c = self.concepts.get(d[lk])
                    if c is not None:
                        d[lk] = c
            for k, v in list(d.items()):
                if isinstance(v, (list, dict)):
                    d[k] = self._dereference_val(v)
            return d
        return val

    def _collect_graph_refs(self, val: Any) -> list:
        """Recursively find str ids or Concept objects inside a relation value."""
        if isinstance(val, (str, Concept)):
            return [val]
        if isinstance(val, (list, tuple)):
            out = []
            for item in val:
                out.extend(self._collect_graph_refs(item))
            return out
        if isinstance(val, dict):
            out = []
            for key in ("target", "id", "concept", "type"):
                if key in val:
                    out.extend(self._collect_graph_refs(val[key]))
            for v in val.values():
                if isinstance(v, (dict, list, tuple)):
                    out.extend(self._collect_graph_refs(v))
            return out
        return []

    def print_graph(self, force: bool = False) -> None:
        """After the KB loads, export an interactive force-directed graph as HTML.

        Opens a nice D3.js force graph visualization in the browser (nodes + edges).
        The graph uses the real resolved Concept pointers (parents + relations like
        needs/produces/hasInstructions/type/hasBody etc.).
        """
        self._export_force_graph_html(force=force)

    def _export_force_graph_html(self, force: bool = False) -> None:
        """Build and write a standalone HTML force graph for the current ontology."""
        out_path = Path(__file__).parent / "kb_graph.html"

        # Skip heavy work if file already exists, unless forcing or env var
        force_export = force or bool(os.environ.get("KB_FORCE_GRAPH") or os.environ.get("KB_EXPORT_GRAPH"))
        if out_path.exists() and not force_export:
            return

        # Collect nodes (all concepts)
        node_list = []
        for cid, c in sorted(self.concepts.items()):
            short = cid.rsplit("/", 1)[-1] if "/" in cid else cid
            node_list.append({
                "id": cid,
                "short": short,
                "kind": c.kind,
                "name": c.name,
            })

        # Collect edges (only between loaded concepts)
        links_set = set()  # (source, target, label) to dedup
        for cid, c in self.concepts.items():
            # parents
            for p in (c.parents or []):
                if isinstance(p, Concept):
                    links_set.add((cid, p.id, "isA"))

            # relations
            for rel_name, val in (c.relations or {}).items():
                for target in self._collect_graph_refs(val):
                    if isinstance(target, Concept):
                        # Use a friendly label for the edge
                        label = rel_name
                        links_set.add((cid, target.id, label))

        link_list = [
            {"source": s, "target": t, "label": lab}
            for (s, t, lab) in sorted(links_set)
        ]

        # Unique kinds for coloring
        kinds = sorted({n["kind"] for n in node_list})

        # Build a simple color palette (deterministic)
        palette = [
            "#4e79a7", "#f28e2c", "#e15759", "#76b7b2", "#59a14f",
            "#edc949", "#af7aa1", "#ff9da7", "#9c755f", "#bab0ab"
        ]
        kind_colors = {k: palette[i % len(palette)] for i, k in enumerate(kinds)}

        # Inline the data as JSON (safe enough here)
        import json as _json
        nodes_json = _json.dumps(node_list, ensure_ascii=False)
        links_json = _json.dumps(link_list, ensure_ascii=False)
        kinds_json = _json.dumps(kinds, ensure_ascii=False)
        colors_json = _json.dumps(kind_colors, ensure_ascii=False)
        node_count = len(node_list)
        link_count = len(link_list)

        # Use plain string + .replace() — completely avoids f-string / JS `${}` parsing issues
        html_template = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Brain KB — Force Graph</title>
<style>
  body { font-family: system-ui, -apple-system, sans-serif; margin: 0; background: #111; color: #ddd; }
  #header {
    position: fixed; top: 0; left: 0; right: 0; z-index: 10;
    background: #1a1a1a; padding: 8px 16px; border-bottom: 1px solid #333;
    display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
  }
  #header h1 { margin: 0; font-size: 18px; }
  #header .stats { color: #888; font-size: 13px; }
  #controls { display: flex; gap: 8px; align-items: center; }
  #search {
    background: #222; color: #ddd; border: 1px solid #444; padding: 4px 8px; border-radius: 4px; width: 240px;
  }
  #legend { display: flex; gap: 8px; flex-wrap: wrap; font-size: 12px; }
  .legend-item { display: flex; align-items: center; gap: 4px; }
  .legend-swatch { width: 12px; height: 12px; border-radius: 2px; }
  #graph-container {
    position: fixed; top: 52px; left: 0; right: 0; bottom: 0;
  }
  svg { width: 100%; height: 100%; background: #0a0a0a; }
  .node circle { stroke: #222; stroke-width: 1.5px; cursor: grab; }
  .node text { fill: #eee; font-size: 9px; pointer-events: none; text-shadow: 0 1px 2px #000; }
  .link { stroke: #555; stroke-opacity: 0.6; }
  .link-label { font-size: 6.5px; fill: #888; pointer-events: none; }
  .node:hover circle { stroke: #fff; }
</style>
</head>
<body>
<div id="header">
  <h1>🧠 Brain KB Force Graph</h1>
  <div class="stats">__NODE_COUNT__ nodes • __LINK_COUNT__ edges</div>
  <div id="controls">
    <input id="search" type="text" placeholder="Filter nodes (id/name/kind)…">
    <button id="reset" style="background:#333;color:#ddd;border:1px solid #555;padding:4px 10px;border-radius:4px;cursor:pointer;">Reset</button>
  </div>
  <div id="legend"></div>
</div>

<div id="graph-container">
  <svg id="graph"></svg>
</div>

<script src="https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js"></script>
<script>
const nodes = __NODES_JSON__;
const links = __LINKS_JSON__;
const kinds = __KINDS_JSON__;
const kindColors = __COLORS_JSON__;

const width = window.innerWidth;
const height = window.innerHeight - 52;

const svg = d3.select("#graph")
  .attr("viewBox", [0, 0, width, height])
  .call(d3.zoom().on("zoom", (event) => {
    g.attr("transform", event.transform);
  }));

// Arrowhead marker for directed edges
svg.append("defs").append("marker")
    .attr("id", "arrow")
    .attr("viewBox", "0 -5 10 10")
    .attr("refX", 14)
    .attr("refY", 0)
    .attr("markerWidth", 6)
    .attr("markerHeight", 6)
    .attr("orient", "auto-start-reverse")
  .append("path")
    .attr("d", "M0,-5L10,0L0,5")
    .attr("fill", "#555");

const g = svg.append("g");

const simulation = d3.forceSimulation(nodes)
  .force("link", d3.forceLink(links).id(d => d.id).distance(90).strength(0.6))
  .force("charge", d3.forceManyBody().strength(-280))
  .force("center", d3.forceCenter(width / 2, height / 2))
  .force("collide", d3.forceCollide(22))
  .force("x", d3.forceX(width / 2).strength(0.05))
  .force("y", d3.forceY(height / 2).strength(0.05));

const link = g.append("g")
  .attr("stroke", "#555")
  .attr("stroke-opacity", 0.55)
  .selectAll("line")
  .data(links)
  .join("line")
  .attr("class", "link")
  .attr("stroke-width", 1.2)
  .attr("marker-end", "url(#arrow)");

const linkLabel = g.append("g")
  .attr("class", "link-label")
  .selectAll("text")
  .data(links)
  .join("text")
  .attr("text-anchor", "middle")
  .attr("dy", -2)
  .attr("paint-order", "stroke")
  .attr("stroke", "#0a0a0a")
  .attr("stroke-width", "2.5px")
  .attr("stroke-linejoin", "round")
  .text(d => d.label);

const node = g.append("g")
  .selectAll("g")
  .data(nodes)
  .join("g")
  .attr("class", "node")
  .call(d3.drag()
    .on("start", dragstarted)
    .on("drag", dragged)
    .on("end", dragended));

node.append("circle")
  .attr("r", 7)
  .attr("fill", d => kindColors[d.kind] || "#888");

node.append("text")
  .attr("dx", 10)
  .attr("dy", 3)
  .text(d => d.short);

node.append("title")
  .text(d => d.id + "\\n" + d.name + " [" + d.kind + "]");

simulation.on("tick", () => {
  link
    .attr("x1", d => d.source.x)
    .attr("y1", d => d.source.y)
    .attr("x2", d => d.target.x)
    .attr("y2", d => d.target.y);

  linkLabel
    .attr("x", d => (d.source.x + d.target.x) / 2)
    .attr("y", d => (d.source.y + d.target.y) / 2);

  node
    .attr("transform", d => "translate(" + d.x + "," + d.y + ")");
});

// Build legend
const legend = d3.select("#legend");
kinds.forEach(k => {
  const item = legend.append("div").attr("class", "legend-item");
  item.append("div")
    .attr("class", "legend-swatch")
    .style("background", kindColors[k] || "#888");
  item.append("span").text(k);
});

function dragstarted(event, d) {
  if (!event.active) simulation.alphaTarget(0.3).restart();
  d.fx = d.x; d.fy = d.y;
}
function dragged(event, d) {
  d.fx = event.x; d.fy = event.y;
}
function dragended(event, d) {
  if (!event.active) simulation.alphaTarget(0);
  d.fx = null; d.fy = null;
}

// Search / filter
const search = document.getElementById("search");
search.addEventListener("input", () => {
  const q = search.value.toLowerCase().trim();
  node.style("opacity", d => {
    if (!q) return 1;
    const hay = (d.id + " " + d.name + " " + d.kind).toLowerCase();
    return hay.includes(q) ? 1 : 0.12;
  });
  link.style("opacity", l => {
    if (!q) return 0.55;
    const sMatch = (l.source.id + " " + (l.source.name||l.source.short) + " " + l.source.kind).toLowerCase().includes(q);
    const tMatch = (l.target.id + " " + (l.target.name||l.target.short) + " " + l.target.kind).toLowerCase().includes(q);
    return (sMatch || tMatch) ? 0.75 : 0.06;
  });
});

document.getElementById("reset").addEventListener("click", () => {
  search.value = "";
  node.style("opacity", 1);
  link.style("opacity", 0.55);
  simulation.alpha(0.6).restart();
});

// Keyboard: press / to focus search
document.addEventListener("keydown", e => {
  if (e.key === "/" && document.activeElement.tagName === "BODY") {
    e.preventDefault();
    search.focus();
  }
});

console.log("Brain KB force graph ready —", nodes.length, "nodes,", links.length, "edges");
</script>
</body>
</html>"""

        html = (html_template
                .replace("__NODE_COUNT__", str(node_count))
                .replace("__LINK_COUNT__", str(link_count))
                .replace("__NODES_JSON__", nodes_json)
                .replace("__LINKS_JSON__", links_json)
                .replace("__KINDS_JSON__", kinds_json)
                .replace("__COLORS_JSON__", colors_json))

        try:
            out_path.write_text(html, encoding="utf-8")
            print(f"[KB] Force graph exported → {out_path}")
            print("     Open the file in any browser (on macOS: open kb_graph.html)")
        except Exception as e:
            print(f"[KB] Failed to write graph HTML: {e}")

_ONTOLOGY: Optional[Ontology] = None


def get_ontology() -> Ontology:
    """Returns the global ontology (loads on first use)."""
    global _ONTOLOGY
    if _ONTOLOGY is None:
        _ONTOLOGY = Ontology()
        # Load *everything* under kb/ so all JSON data (triplets, plan templates,
        # constructs, recipes, biology/chemistry/etc. domains, etc.) is available.
        # The loader skips files without "id" (e.g. pure triplet facts) gracefully.
        kb_root = Path(__file__).parent / "kb"
        _ONTOLOGY.load_from_directory(kb_root)
        logger.info("Ontology loaded with %d concepts", len(_ONTOLOGY))
        # On first creation of the ontology in this process, always (re)generate the graph HTML.
        _ONTOLOGY.print_graph(force=True)
    else:
        # If the graph file was deleted since last load in this process, recreate it.
        graph_file = Path(__file__).parent / "kb_graph.html"
        if not graph_file.exists():
            _ONTOLOGY.print_graph()
    return _ONTOLOGY


def get_concept(concept_id: str) -> Optional[Concept]:
    """Primary way to retrieve knowledge."""
    logger.debug("get_concept called for: %s", concept_id)
    return get_ontology().get(concept_id)


def load_ontology(force_reload: bool = False) -> Ontology:
    """Explicitly (re)load the ontology. Useful for development."""
    logger.debug("load_ontology called (force_reload=%s)", force_reload)
    global _ONTOLOGY
    if force_reload:
        _ONTOLOGY = None
    return get_ontology()
