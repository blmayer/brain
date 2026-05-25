"""Knowledge Base — Ontology First

We now use the new Golang ontology format exclusively.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any, Optional


@dataclass
class Concept:
    """A concept loaded from the ontology JSON files."""
    id: str
    kind: str
    name: str
    parents: List[str] = field(default_factory=list)
    relations: Dict[str, Any] = field(default_factory=dict)
    emitters: List[Dict[str, Any]] = field(default_factory=list)
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

    def find_concepts_matching(self, keywords: list[str] | str) -> list[Concept]:
        """
        Find concepts whose id, name, or relations mention any of the keywords.
        Used to go from parsed words (e.g. "print", "reads", "sum") to ontology Concepts.
        """
        if isinstance(keywords, str):
            keywords = [keywords]

        keywords = [k.lower() for k in keywords]
        results = []

        for concept in self.concepts.values():
            text = " ".join([
                concept.id.lower(),
                concept.name.lower(),
                str(concept.relations).lower(),
                str(concept.raw).lower()
            ])
            if any(kw in text for kw in keywords):
                results.append(concept)

        return results

    def find_related_concepts(self, concept: Concept, relation_names: list[str] = None) -> list[Concept]:
        """
        Given a concept, follow its relations to find other concepts it depends on or is related to.
        Example: for a "print" concept, find the actual "fmt.Println" implementation concept.
        """
        if relation_names is None:
            relation_names = ["needs", "hasParameter", "importsPackage", "relatedTo", "implementedBy"]

        related = []
        rels = concept.relations or {}

        for rel_name in relation_names:
            targets = rels.get(rel_name, [])
            if isinstance(targets, dict):
                targets = [targets]

            for target in targets:
                if isinstance(target, dict):
                    target_id = target.get("target") or target.get("id")
                    if target_id and target_id in self.concepts:
                        related.append(self.concepts[target_id])
                elif isinstance(target, str) and target in self.concepts:
                    related.append(self.concepts[target])

        return related

    def find_producers_of_type(self, target_type: str) -> list[Concept]:
        """
        Find concepts in the ontology that can produce a value/binding of the given type.
        Used for proper dependency satisfaction.
        """
        producers = []
        target_type = target_type.lower()

        for concept in self.concepts.values():
            rels = concept.relations or {}

            for prod in rels.get("produces", []):
                if isinstance(prod, dict):
                    ptype = prod.get("type", "").lower()
                    if ptype == target_type or ptype == "any":
                        producers.append(concept)
                        break
                elif isinstance(prod, str) and prod.lower() == target_type:
                    producers.append(concept)
                    break

            raw_str = str(concept.raw).lower()
            if target_type in raw_str and "return" in raw_str:
                if concept not in producers:
                    producers.append(concept)

        return producers

    def find_implementations_of(self, concept_id: str) -> list[Concept]:
        """
        Given a concept id (e.g. "PrintOperation"), return all concepts that
        specialize or implement it (e.g. "fmt.Println").
        """
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
                    if isinstance(t, dict):
                        tid = t.get("target") or t.get("id")
                    else:
                        tid = t
                    if tid == concept_id:
                        implementations.append(concept)
                        break

        return implementations

    def load_from_directory(self, base_path: Path):
        if not base_path.exists():
            return

        for json_file in base_path.rglob("*.json"):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                if isinstance(data, dict) and "instances" in data:
                    for item in data["instances"]:
                        self._load_single_concept(item, json_file)
                else:
                    self._load_single_concept(data, json_file)

                self.loaded_paths.append(json_file)
            except Exception as e:
                print(f"[Ontology] Failed to load {json_file}: {e}")

    def _load_single_concept(self, data: Dict, source: Path):
        if not isinstance(data, dict) or "id" not in data:
            return

        concept = Concept(
            id=data["id"],
            kind=data.get("kind", "UNKNOWN"),
            name=data.get("name", data["id"]),
            parents=data.get("parents", []),
            relations=data.get("relations", {}),
            emitters=data.get("emitters", []),
            raw=data,
        )
        self.register(concept)

    def __len__(self):
        return len(self.concepts)


_ONTOLOGY: Optional[Ontology] = None


def get_ontology() -> Ontology:
    """Returns the global ontology (loads on first use)."""
    global _ONTOLOGY
    if _ONTOLOGY is None:
        _ONTOLOGY = Ontology()
        base = Path(__file__).parent / "kb" / "ontology" / "golang"
        _ONTOLOGY.load_from_directory(base / "constructs")
        _ONTOLOGY.load_from_directory(base / "examples")
        print(f"[kb] Ontology loaded with {len(_ONTOLOGY)} concepts")
    return _ONTOLOGY


def get_concept(concept_id: str) -> Optional[Concept]:
    """Primary way to retrieve knowledge."""
    return get_ontology().get(concept_id)


def load_ontology(force_reload: bool = False) -> Ontology:
    global _ONTOLOGY
    if force_reload:
        _ONTOLOGY = None
    return get_ontology()
