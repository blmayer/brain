# Recipe Interface Examples

This directory demonstrates the new **interface satisfaction** feature.

## Key Ideas

- `Recipe` is an INTERFACE (kind: "INTERFACE").
- Concrete recipes (e.g. `fried_egg`) declare `hasIngredients` and `hasInstructions`.
- An ingredient requirement can be a **class** (`isClass: true`). In that case any instance of the class satisfies it.
  - Example: `spices` requirement is satisfied by `salt` or `pepper` because they have `parents: ["Spice"]`.

## Usage in the pipeline

After `add_concepts` + dependency resolution, `apply_interface_satisfaction` (called automatically from `_features_to_plan`) will look for nodes that declare Recipe-style requirements and, given a pool of available items, will annotate satisfying candidates with:

```json
{ "isA": "recipe", "satisfied_interfaces": ["Recipe"] }
```

See the test `test_interface_satisfaction_fried_egg` in `test_augment.py` for a complete worked example.
