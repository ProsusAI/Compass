# Route Exclusion Writing Guidelines

A `route_exclusion` explains why a specific route was not assigned to a query. Every exclusion must reference observable properties of the query itself — not what any route target is capable of.

---

## DO: Reference Observable Query Properties

Exclusions must be grounded in what is visible in the query text.

| Good | Why it works |
|---|---|
| "Query requires joining results from three independent data sources." | Cites a structural property of the task (multi-source join). |
| "Query asks for a creative narrative with no factual lookup required." | Describes the query's output goal directly. |
| "Query contains a single well-formed lookup with no ambiguity." | References query structure and clarity. |
| "Query specifies real-time data that must be retrieved, not generated." | Points to an explicit constraint in the query. |

---

## DON'T: Reference Route Target Capabilities

Exclusions must not explain a route's limitations or internal workings.

| Bad | Why it fails |
|---|---|
| "This route cannot handle multi-step reasoning." | Describes the route, not the query. |
| "That route lacks web access." | States a capability gap, not a query property. |
| "The assigned route is better at creative tasks." | Explains the winner, not the loser. |
| "This route is too expensive for this simple query." | Cost or resource reasoning is not a query property. |

---

## Route Field Requirements

- The `route` field must be copied verbatim from `routing_context.routes`.
- Do not paraphrase, abbreviate, or translate route identifiers. They are opaque strings.

**Correct:**
```yaml
route: "search-grounded"
```

**Incorrect:**
```yaml
route: "search grounded"   # wrong: spaces instead of hyphens
route: "search"            # wrong: abbreviated
route: "Search-Grounded"   # wrong: wrong case
```

---

## Structural Requirements

- Each `reason` is a **single sentence** — no conjunctions that create compound sentences.
- Each `reason` is **non-empty** — a blank or placeholder string is an annotation error.
- **Coverage**: every route in `routing_context.routes` that is not the `ground_truth_route` must have at least one exclusion entry.

**Correct (one route, one reason):**
```yaml
- route: "fast-route"
  reason: "Query requires synthesising conflicting information across five documents."
```

**Correct (one route, two reasons):**
```yaml
- route: "fast-route"
  reason: "Query requires synthesising conflicting information across five documents."
- route: "fast-route"
  reason: "Query explicitly requests a comparison table, which requires structured multi-pass reasoning."
```

**Incorrect (compound sentence):**
```yaml
- route: "fast-route"
  reason: "Query is complex and it also requires multiple retrieval steps."  # two claims in one sentence
```
