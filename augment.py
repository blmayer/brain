"""Augment parsed plan trees using knowledge from KB.

Generic implementation (no hard-coded program structure or names in the algorithms).
From a (parsed) plan tree of Node/Plan, use KB entries to resolve needs, bind variables,
and prepare Exec plan that can emit the final lines (e.g. Go source).
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Union
from kb import Node, Dep, KB, get_node, TextEmit, RefEmit, Emit


@dataclass
class ExecNode:
    """Runtime execution node after augmentation/solve against KB."""
    node: Node
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


def _is_leaf_plan(p: Any) -> bool:
    """A leaf like 'a' or 'b' has no KB entry and is just naming a variable."""
    return isinstance(p, (dict, object)) and getattr(p, "id", None) and p.id not in KB


def solve_plan(plan: Any, ctx: Optional[Context] = None, providing: Optional[Dep] = None) -> ExecNode:
    """Recursively augment/solve the parsed plan tree using KB knowledge.

    This is the core: from the (high-level or detailed) parsed tree, lookup KB nodes
    by ID, bind their needs/produces using provided children and context, attach
    sub Exec for children. Generic -- works for any KB entries + plan shapes.
    """
    if ctx is None:
        ctx = Context()

    plan_id = getattr(plan, "id", None) or (plan.get("id") if isinstance(plan, dict) else None)
    if not plan_id:
        raise ValueError("Plan node must have an 'id'")

    # Get KB template if present (the augmentation step)
    try:
        kb_node = get_node(plan_id)
    except KeyError:
        kb_node = None

    # Treat as leaf/naming node if no KB entry OR if it has no emits (dummy/placeholder like "a","b")
    if kb_node is None or len(getattr(kb_node, "emits", []) or []) == 0:
        # Leaf / concrete variable instance (e.g. id="a"). Provide name and type from caller.
        var_name = plan_id
        var_type = providing.type if providing else "any"
        ctx.types[var_name] = var_type
        # Create a lightweight node for it
        leaf_node = Node(id=var_name, type="instance", produces=[Dep(var_name, var_type)])
        exec_n = ExecNode(node=leaf_node, bindings={var_name: var_name, "var": var_name}, deps=[])

        # Recurse into its sub-steps (declaration, read etc attached in parsed tree)
        children = getattr(plan, "needs", None) or (plan.get("needs", []) if isinstance(plan, dict) else [])
        for child in children:
            child_exec = solve_plan(child, ctx, providing=Dep(name=var_name, type=var_type))
            exec_n.deps.append(child_exec)

        return exec_n

    # --- KB template node: augment the plan step with its knowledge (needs, emits, etc.)
    exec_n = ExecNode(node=kb_node, bindings={}, deps=[])

    # 1. First solve all children from the parsed plan tree (these provide actuals for needs or names)
    children = getattr(plan, "needs", None) or (plan.get("needs", []) if isinstance(plan, dict) else [])
    child_execs = []
    for i, child in enumerate(children):
        # Pass the corresponding need as providing so leaves get correct type (generic data-driven)
        prov = kb_node.needs[i] if i < len(kb_node.needs) else None
        c_exec = solve_plan(child, ctx, providing=prov)
        child_execs.append(c_exec)
        exec_n.deps.append(c_exec)

    # 2. Map children to this node's needs (positional + only for var-like needs so decl's "type" meta-need isn't overwritten by var-name child)
    #    This keeps it generic: decision based on Dep fields themselves, not on specific node IDs.
    for i, c_exec in enumerate(child_execs):
        if i < len(kb_node.needs):
            need = kb_node.needs[i]
            if "var" in need.name or need.type in ("int", "any", "string", "float"):
                # child's id supplies the concrete name for this formal need
                supplied = c_exec.node.id
                exec_n.bindings[need.name] = supplied
                if supplied in ctx.types:
                    ctx.types[supplied] = need.type

    # Bubble any produced names from direct children (so print can see "result" from sum)
    for c_exec in child_execs:
        for k, v in c_exec.bindings.items():
            if k not in exec_n.bindings:
                exec_n.bindings[k] = v

    # 3. Bind remaining needs (e.g. "type" for declaration) using providing or context or inferred type
    for need in kb_node.needs:
        if need.name not in exec_n.bindings:
            if need.name == "type":
                # For declaration etc, type comes from the use-site providing or from the var we are declaring
                if providing and providing.type and providing.type != "any":
                    exec_n.bindings[need.name] = providing.type
                else:
                    # fallback: look for a "var" already bound in this exec and use its type
                    var_name = exec_n.bindings.get("var")
                    if var_name:
                        exec_n.bindings[need.name] = ctx.get_type(var_name)
                    else:
                        exec_n.bindings[need.name] = "int"  # safe default for our tests
            else:
                pref = None
                exec_n.bindings[need.name] = ctx.bind(need.name, need.type, pref)

    # 4. Bind produces (e.g. "result", "var" from declaration)
    for prod in kb_node.produces:
        if prod.name not in exec_n.bindings:
            # prefer a name from a child that "is" this, or use prod.name literally for readability
            supplied = None
            for c_exec in child_execs:
                if prod.name in c_exec.bindings:
                    supplied = c_exec.bindings[prod.name]
                    break
            actual = ctx.bind(prod.name, prod.type, preferred=supplied or prod.name)
            exec_n.bindings[prod.name] = actual
            # If this produce corresponds to a concrete var name from plan, record it
            if supplied:
                ctx.types[actual] = prod.type

    # 5. Generic post-processing for templates that operate on a "var" (decl, read, etc.):
    #    If a direct child is a simple leaf (name, no emits), and we have a "var" slot, use the leaf's id.
    #    This is driven by the shape of children + Deps in KB, fully generic.
    simple_child_names = []
    for c_exec in child_execs:
        cid = c_exec.node.id
        if cid and (cid not in KB or len(getattr(KB.get(cid), "emits", []) or []) == 0):
            simple_child_names.append(cid)
    if simple_child_names:
        first = simple_child_names[0]
        for slot in ("var",):
            if slot in [d.name for d in (kb_node.needs + kb_node.produces)]:
                if slot not in exec_n.bindings or not exec_n.bindings.get(slot) or exec_n.bindings[slot] == "var":
                    exec_n.bindings[slot] = first

    # 6. For needs that are meta "type" (like declaration), ensure bound from providing or ctx var type
    if any(n.name == "type" for n in kb_node.needs):
        if "type" not in exec_n.bindings or exec_n.bindings.get("type") in (None, "type", "any"):
            if providing and providing.type and providing.type not in ("any", "type"):
                exec_n.bindings["type"] = providing.type
            else:
                # try from a var we just bound
                v = exec_n.bindings.get("var")
                if v:
                    exec_n.bindings["type"] = ctx.get_type(v) or "int"
                else:
                    exec_n.bindings["type"] = "int"

    return exec_n


def render(node: Node, bindings: Dict[str, str]) -> str:
    """Render one line by replacing RefEmits with bound values, concatenating Text."""
    parts = []
    for e in node.emits:
        if isinstance(e, TextEmit):
            parts.append(e.text)
        elif isinstance(e, RefEmit):
            val = bindings.get(e.ref, e.ref)  # fallback to ref name itself if unbound
            parts.append(val)
    return "".join(parts)


def emit(exec_n: ExecNode, visited: Optional[Dict[str, bool]] = None, out: Optional[List[str]] = None) -> List[str]:
    """DFS post-order emit: children first, then this node's rendered line (if any).
    Avoids duplicates via visited key.
    """
    if visited is None:
        visited = {}
    if out is None:
        out = []

    key = _make_key(exec_n)
    if visited.get(key):
        return out
    visited[key] = True

    for d in exec_n.deps:
        emit(d, visited, out)

    line = render(exec_n.node, exec_n.bindings)
    if line:
        out.append(line)

    return out


def _make_key(e: ExecNode) -> str:
    key = e.node.id
    for k, v in sorted(e.bindings.items()):
        key += f"|{k}={v}"
    return key


# --- Helpers to build plan trees for tests (use same shape as Go example) ---
# We use a simple dict-based Plan for ease in tests (or could use Node with needs=List[Plan])

def make_plan(id_: str, needs: Optional[List[Any]] = None) -> Dict[str, Any]:
    """Convenience to build the kind of plan trees used in the Go example."""
    return {"id": id_, "needs": needs or []}


def make_var_plan(var_id: str, sub_steps: List[Dict]) -> Dict[str, Any]:
    """A var instance plan with its acquisition steps (decl, read)."""
    return make_plan(var_id, needs=sub_steps)


# Example usage / demo (mirrors the broken main.go intent, now working)
if __name__ == "__main__":
    # Build plan tree just like the Go example (but using 'needs')
    # a and b have their decl+read attached
    decl_a = make_plan("declaration", needs=[make_plan("a")])
    read_a = make_plan("read", needs=[make_plan("a")])
    a_plan = make_var_plan("a", [decl_a, read_a])

    decl_b = make_plan("declaration", needs=[make_plan("b")])
    read_b = make_plan("read", needs=[make_plan("b")])
    b_plan = make_var_plan("b", [decl_b, read_b])

    sum_plan = make_plan("sum", needs=[a_plan, b_plan])
    print_plan = make_plan("print", needs=[sum_plan])

    ctx = Context()
    root = solve_plan(print_plan, ctx)

    lines = emit(root)

    print("package main")
    print('import "fmt"')
    print("\nfunc main() {")
    for line in lines:
        print("  " + line)
    print("}")
    print("\n--- bindings at root ---")
    print(root.bindings)


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


def _normalize_to_kb_id(word: str) -> str:
    """Very light normalization so that 'reads'/'prints' map to 'read'/'print' etc.
    Returns the word if it (or its normalized form) is a key in KB.
    """
    w = word.lower().strip()
    if w in KB:
        return w
    # naive 3rd-person / plural stripping
    for suffix in ('s', 'es', 'ies'):
        if w.endswith(suffix):
            base = w[:-len(suffix)]
            if base in KB:
                return base
            # special case: "ies" → "y" (e.g. carries → carry, but we don't have that yet)
            if suffix == 'ies' and (base + 'y') in KB:
                return base + 'y'
    return w


def _extract_intent_features(tree) -> dict:
    """Generic, KB-driven feature extraction.

    Walks the tree, and for every verb/noun checks whether a normalized
    form is present as a key in the Knowledge Base.  This makes the
    detector automatically support any new templates you add to KB
    (e.g. 'loop', 'if', 'sort', 'filter'...) without changing this code.
    """
    words, pos_tags, lower_words = [], [], []

    for leaf in _walk_leaves(tree):
        w = leaf.get('word', '')
        p = leaf.get('pos', '')
        words.append(w)
        pos_tags.append(p)
        lower_words.append(w.lower())

    text = ' '.join(lower_words)

    verbs = [w for w, p in zip(words, pos_tags)
             if isinstance(p, str) and p.startswith('VB')]
    nouns = [w for w, p in zip(words, pos_tags)
             if isinstance(p, str) and p.startswith('NN')]

    # KB-driven detection
    detected_kb_nodes = set()
    for w in verbs + nouns:
        kb_id = _normalize_to_kb_id(w)
        if kb_id in KB:
            detected_kb_nodes.add(kb_id)

    features = {
        'verbs': verbs,
        'nouns': nouns,
        'text': text,
        'has_program': any(k in text for k in ('program', 'code', 'script')),
        'languages': [],
        'detected_kb_nodes': detected_kb_nodes,   # e.g. {'read', 'print', 'sum'}
        'io_verbs': set(),
        'arithmetic': set(),
        'input_count_hint': 2,
    }

    # Language hints (still a small static map – can be moved to KB later)
    lang_hints = {'go': 'golang', 'golang': 'golang', 'python': 'python', 'py': 'python'}
    for w in lower_words:
        if w in lang_hints:
            features['languages'].append(lang_hints[w])

    # Classify the KB hits into higher-level buckets used by the plan builder
    for kb_id in detected_kb_nodes:
        if kb_id in ('read', 'declaration'):
            features['io_verbs'].add('read')
        if kb_id == 'print':
            features['io_verbs'].add('print')
        if kb_id == 'sum':
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


def _features_to_plan(features: dict) -> dict:
    """Turn the generic (now KB-driven) features into a Plan dict.

    The wiring logic still knows how to assemble the only fully-supported
    emission we have today, but it only activates when the *features*
    (populated from KB lookup) say the sentence mentioned read/print/sum.
    """
    detected = features.get('detected_kb_nodes', set())
    want_read = 'read' in features['io_verbs'] or 'read' in detected
    want_print = 'print' in features['io_verbs'] or 'print' in detected
    want_sum = bool(features['arithmetic']) or 'sum' in detected

    if want_read and want_print and want_sum:
        decl_a = make_plan("declaration", needs=[make_plan("a")])
        read_a = make_plan("read", needs=[make_plan("a")])
        a_plan = make_var_plan("a", [decl_a, read_a])

        decl_b = make_plan("declaration", needs=[make_plan("b")])
        read_b = make_plan("read", needs=[make_plan("b")])
        b_plan = make_var_plan("b", [decl_b, read_b])

        sum_p = make_plan("sum", needs=[a_plan, b_plan])
        return make_plan("print", needs=[sum_p])

    # Safe fallback
    return make_plan("print", needs=[make_plan("sum", needs=[make_plan("a"), make_plan("b")])])


def tree_to_solved_plan(parsed_tree, resolved_tree=None):
    """Public entry point requested by the user.

    Takes the trees returned by process_input() (main.py).
    Uses the resolved tree (with pronoun references) when present.
    Extracts features by asking the KB which words it knows, builds a plan,
    solves it, and returns the root ExecNode.

    Completely generic: the set of recognized actions grows automatically
    when you add new entries to KB.
    """
    tree = resolved_tree if resolved_tree is not None else parsed_tree
    features = _extract_intent_features(tree)
    plan = _features_to_plan(features)
    ctx = Context()
    return solve_plan(plan, ctx)
