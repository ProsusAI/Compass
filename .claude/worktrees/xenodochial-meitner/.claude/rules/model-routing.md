## Model Routing

- **Planning and design**: Use the main conversation (Opus 4.6) for planning, architecture decisions, code review, and reasoning tasks.
- **Implementation**: Delegate code writing, editing, and refactoring to Agent subagents with `model: "sonnet"`.
- **Git actions**: Delegate all git operations (commits, PRs, branch management) to Agent subagents with `model: "haiku"`.

When a task involves both planning and implementation, do the planning/analysis in the main conversation first, then delegate the implementation to a Sonnet agent with clear, specific instructions based on that analysis.
