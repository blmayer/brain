"""Knowledge Base for Python implementation of plan augmentation.

Uses Node with 'needs' (renamed from Depends, sounds better) for requirements.
This holds sample knowledge nodes translated from kb/ JSONs for code gen assembly.
Generic: data driven, no logic hardcodes.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Union, Any


@dataclass(frozen=True)
class TextEmit:
    """Emits literal text in the output."""
    text: str


@dataclass(frozen=True)
class RefEmit:
    """Emits a reference to a bound variable/name from context."""
    ref: str


Emit = Union[TextEmit, RefEmit]


@dataclass(frozen=True)
class Dep:
    """A dependency or produce spec: name and its type/kind.
    Replaces the old Depends entries which were {Name, Type}.
    """
    name: str
    type: str


@dataclass
class Node:
    """Core knowledge node from KB.

    - id: unique identifier, e.g. "sum", "print", "declaration"
    - type: "instance" or other (for variables etc)
    - needs: list of Deps this step requires (renamed from Depends -- sounds better)
    - produces: list of Deps this step yields
    - emits: list of Emit (Text or Ref) to render the code line when all bound
    - context, confidence, source, date: provenance
    """
    id: str
    type: str = "instance"
    needs: List[Dep] = field(default_factory=list)
    produces: List[Dep] = field(default_factory=list)
    emits: List[Emit] = field(default_factory=list)
    context: str = ""
    confidence: float = 1.0
    source: str = ""
    date: str = ""


# Sample KB populated from the JSON knowledge (operators/syntax for Go codegen).
# This is "some knowledge in a python file".
# In real, this would be loaded from kb/*.json but for step 1 we embed generic data.
# The logic using it must remain generic.

KB: Dict[str, Node] = {
    "sum": Node(
        id="sum",
        needs=[
            Dep(name="var_a", type="int"),
            Dep(name="var_b", type="int"),
        ],
        produces=[
            Dep(name="result", type="int"),
        ],
        emits=[
            RefEmit(ref="result"),
            TextEmit(text=" := "),
            RefEmit(ref="var_a"),
            TextEmit(text=" + "),
            RefEmit(ref="var_b"),
        ],
        context="golang",
        confidence=0.95,
        source="brain_v2",
        date="2026-04-28",
    ),
    "print": Node(
        id="print",
        needs=[
            Dep(name="var", type="any"),
        ],
        produces=[],
        emits=[
            TextEmit(text="fmt.Println("),
            RefEmit(ref="result"),  # note: result comes via parent binding from sum dep
            TextEmit(text=")"),
        ],
        context="golang",
        confidence=0.95,
        source="brain_v2",
        date="2026-04-28",
    ),
    "declaration": Node(
        id="declaration",
        needs=[
            Dep(name="type", type="type"),
        ],
        produces=[
            Dep(name="var", type="any"),
        ],
        emits=[
            TextEmit(text="var "),
            RefEmit(ref="var"),
            TextEmit(text=" "),
            RefEmit(ref="type"),
        ],
        context="golang",
        confidence=0.95,
        source="brain_v2",
        date="2026-04-28",
    ),
    "read": Node(
        id="read",
        needs=[
            Dep(name="var", type="any"),
        ],
        produces=[],
        emits=[
            TextEmit(text='fmt.Scanf("%d", &'),
            RefEmit(ref="var"),
            TextEmit(text=")"),
        ],
        context="golang",
        confidence=0.95,
        source="brain_v2",
        date="2026-04-28",
    ),
    # Note: variable instances like "a", "b" are not stored as emitting KB entries;
    # they are provided by the parsed plan tree and treated as leaves (name providers).
    # The KB only contains the generic templates (sum, print, declaration, read).
}


def get_node(node_id: str) -> Node:
    """Generic lookup in KB. Returns copy or the node."""
    if node_id not in KB:
        raise KeyError(f"Unknown node in KB: {node_id}")
    return KB[node_id]


# For now, the KB is the source of truth for augmentation.
# Later we can add loader from json/ dir that converts Depends->needs etc.
