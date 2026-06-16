"""KB Graph — Node/link HTML visualization exporter.

Extracted from kb.py to keep the core ontology focused on data and queries.
"""

from pathlib import Path
import os
import json as _json
from typing import Any

# Absolute import: when this module is loaded (via "import kb_graph" from kb.py),
# kb is already present on sys.modules so this succeeds. No package-relative dots.
import kb
Concept = kb.Concept
Ontology = kb.Ontology


def _collect_graph_refs(val: Any) -> list:
    """Recursively find str ids or Concept objects inside a relation value."""
    if isinstance(val, (str, Concept)):
        return [val]
    if isinstance(val, (list, tuple)):
        out = []
        for item in val:
            out.extend(_collect_graph_refs(item))
        return out
    if isinstance(val, dict):
        out = []
        for key in ("target", "id", "concept", "type"):
            if key in val:
                out.extend(_collect_graph_refs(val[key]))
        for v in val.values():
            if isinstance(v, (dict, list, tuple)):
                out.extend(_collect_graph_refs(v))
        return out
    return []


def export_force_graph_html(ontology: Ontology, force: bool = False) -> None:
    """Build and write a standalone HTML force graph for the current ontology.

    The graph uses the real resolved Concept pointers (parents + relations like
    needs/produces/hasInstructions/type/hasBody etc.).
    """
    out_path = Path(__file__).parent / "kb_graph.html"

    # Skip heavy work if file already exists, unless forcing or env var
    force_export = force or bool(os.environ.get("KB_FORCE_GRAPH") or os.environ.get("KB_EXPORT_GRAPH"))
    if out_path.exists() and not force_export:
        return

    # Collect nodes (all concepts)
    node_list = []
    for cid, c in sorted(ontology.concepts.items()):
        short = cid.rsplit("/", 1)[-1] if "/" in cid else cid
        node_list.append({
            "id": cid,
            "short": short,
            "kind": c.kind,
            "name": c.name,
        })

    # Collect edges (only between loaded concepts)
    links_set = set()  # (source, target, label) to dedup
    for cid, c in ontology.concepts.items():
        # parents
        for p in (c.parents or []):
            if isinstance(p, Concept):
                links_set.add((cid, p.id, "isA"))

        # relations
        for rel_name, val in (c.relations or {}).items():
            for target in _collect_graph_refs(val):
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
  d.fx = event.x; d.fy = d.y;
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
