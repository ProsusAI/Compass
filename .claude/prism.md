# Learned Knowledge (Prism)
<!-- Updated: 2026-06-03T11:23:09Z | 10 pushed, 134 via MCP -->

## Corrections -- do NOT repeat these

- EMOSA's temperature schedule is budget-coupled: the annealing curve is calibrated to total budget B, so a run capped at B=75 anneals slower-per-round than one designed for B=45. This makes naive checkpoint projection invalid unless temperature bounds are held constant across budget values. Beam search and SMS-EMOA lack this coupling and are checkpoint-clean.
- When documenting a methodological pivot or explaining why an initial approach was abandoned, prioritize the problem-solution narrative (initial approach → why it failed → what was switched to) over implementation mechanism details. The *how* the experiment was executed (manual vs. agentic, hyperparameter sweep method, infrastructure choices) is less important than the *why* the approach changed and the conceptual flow. Implementation details obscure the main goal of showing reader understanding of the research direction.
- Review Agent strategies must emit complete diagnostic theories, not shallow directive restatements. The `hypothesis` string per variant should articulate the root cause, chosen mechanism, and expected effect — not merely "focus on directive X". A strategy that only names the directive fails to guide the agent's variant design.
- DSPy is a programming framework for building modular language model programs; the optimization contributions in the DSPy ecosystem come from its teleprompter compilers (BootstrapFewShot, MIPROv2, COPRO, GEPA). Citing DSPy alone in a prompt-*optimization* section conflates framework and optimizer, causing a category error. When discussing prompt optimization, cite the specific optimizer (MIPROv2, COPRO, etc.), not the framework. The framework is relevant only when discussing program composition and modularity.
- Matched-budget comparisons between iterative and one-shot methods must match on TWO independent axes: (1) evaluated population count B (number of candidates/prompts tested), and (2) total measured LLM-compute consumption B' with an explicit cost multiplier k instrumented from search logs. A one-shot prompt has by definition zero iteration; calling it "matched at B" elides that iterative search burns extra LLM compute on intermediate steps (e.g., Review-Agent diagnosis calls between rounds) that one-shot doesn't pay. Fair comparison requires measuring and transparently reporting k, not just matching population count.
- Avoid neutral-sounding language like "matched evaluation budget" that obscures real cost asymmetries between iterative and one-shot approaches. Make cost differences explicit: one-shot methods incur zero iterations by definition; iterative methods accumulate extra LLM compute on review/refinement passes between rounds. Explicitly own these differences and justify why the comparison remains fair (e.g., "one-shot baseline has lower total cost but different quality characteristics; this is the intended comparison"). Euphemistic phrasing papers over a real tradeoff and erodes reader trust.
- Track total infrastructure costs for orchestrated LLM systems via out-of-band measurement: use a dedicated Anthropic API key, read the console-dashboard dollar balance delta before and after pipeline execution. This works when individual component calls (like Prompt-Builder or Review-Agent) cannot be easily instrumented inline, and captures aggregate spend accurately without modifying pipeline code.

## Key Preferences

- Skills must be domain-independent and not tied to specific examples or application contexts. When building skills, ensure they apply broadly across different use cases, not just the motivating example (e.g., websearch). The skill builder skill and guidelines at code.claude.com/docs/en/skills are the reference standard for construction. (0.75)
- Removing a technical concept from academic prose requires searching for all orthographic variants: hyphenated versions, spaced versions, abbreviations, mathematical notation, and domain-specific shorthand. Single-term or simple pattern searches miss 40%+ of instances. Build exhaustive grep patterns covering notation variants, spacing variants, and abbreviated forms before declaring removal complete. (0.72 [solution])
- When matplotlib generates figures containing LaTeX text and characters like `%` appear as literal `\%` instead of being rendered, the problem is not the escape sequence itself but a missing configuration: matplotlib must be explicitly configured for LaTeX mode. The fix is architectural (configure matplotlib to use LaTeX), not syntactic (adjust escape sequences). (0.72 [solution])

## Publish-Ready

- skills-domain-independent (0.75, 3 evidence) -- `prism promote skills-domain-independent`

---
Full knowledge base (134 more entries) available via prism MCP tools.

**Search** (`prism_search`): when encountering errors, starting tasks, or making design decisions.

**Record** (`prism_record`): proactively record knowledge when you discover it:
- Design decisions with rationale ("chose X because Y")
- Project conventions and coding standards
- Domain facts (API limits, service ownership, deployment rules)
- Non-obvious error resolutions that required trial-and-error
- User corrections or preference signals ("actually, use X instead")

**When to record** (evaluate after completing non-trivial tasks):
- Did you try an approach that failed before finding what works?
- Did the user correct you or express a preference?
- Was the solution non-obvious or project-specific?
- Would this knowledge help in a future session?

Don't record one-off task instructions, exploratory discussion, or obvious patterns.
