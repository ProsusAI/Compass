# Vocabulary Registry Rules

These rules govern all three vocabularies used in routing rationale annotation: `intent_pattern`, `complexity_structure`, and `ambiguity_tags`.

---

## Naming Conventions

| Vocabulary | Convention | Example |
|---|---|---|
| `intent_pattern` | kebab-case | `multi-source-aggregation` |
| `complexity_structure` | kebab-case | `sequential-dependency` |
| `ambiguity_tags` | SCREAMING_SNAKE_CASE | `BOUNDARY_CASE` |

---

## Cluster Threshold

A new entry may only be added to the registry when enough dataset examples would use it:

```
min_cluster_size = max(3, ceil(0.05 * dataset_size))
```

An annotator may **propose** an entry before this threshold is met (so examples are collected), but the entry must not be treated as confirmed until the threshold is reached. Threshold enforcement happens during post-loop validation, not during per-example annotation.

---

## Semantic Overlap

Before proposing a new entry, verify that no existing entry covers the same meaning under a different label. A new entry is only justified when:

1. The concept is genuinely distinct from all existing entries, and
2. The justification clearly states why existing entries are insufficient.

Entries that differ only in surface framing (e.g., "document-summarisation" vs "text-condensation") are considered overlapping.

---

## Append-Only Policy

The registry is append-only across annotation runs. Existing entries must not be renamed, redefined, or removed once confirmed. If an entry proves too broad, add a more specific entry alongside it rather than modifying the original.

---

## Required Fields for New Entries

Every proposed or confirmed entry must include all of the following fields:

| Field | Description |
|---|---|
| `name` | Identifier following the naming convention above |
| `definition` | One-sentence description of what the entry covers |
| `example_ids` | List of dataset example IDs that use this entry |
| `justification` | Why no existing registry entry is sufficient |

Entries missing any required field are invalid and must not be used in annotation output.
