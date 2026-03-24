When changes affect agent prompts, MCP surface (tools/prompts/resources), shared models,
context dict keys, or cross-module interfaces, update the relevant documentation
(docs/architecture.md and module READMEs) in the same commit.

Style guidance:
- Prefer tables over prose for structured information (agent lists, context keys, model fields)
- Match the heading structure and formatting of the doc you're updating
- Keep descriptions concise — one sentence where one sentence suffices
- Use consistent formatting: backticks for code references, links to source files
- No padding — length should match complexity, not fill a template

Do not commit interface changes with stale docs.
