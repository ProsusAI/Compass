# Integration Test Scenarios

Test scenarios for the User Input agent. Each `.md` file in this directory is a self-contained test scenario executed by Claude Code.

## Prerequisites

- The Odysseus MCP server must be pre-configured and connected to Claude Code before running tests.
- Real LLM API calls are made — ensure `ANTHROPIC_API_KEY` is set.

## How to run a scenario

Tell Claude Code:

> Run the integration test in `tests/scenarios/01_complete_submission.md`

Claude Code will:

1. Read the scenario file and parse its sections.
2. Spin up a **User Simulator** sub-agent with the `## User Simulator` section as its instructions.
3. Spin up a **User Input Agent** sub-agent with `prompts/user_input_system.md` as its system prompt, connected to the MCP tools.
4. Get the opening message from the User Simulator.
5. Broker the conversation turn-by-turn:
   - Pass user message → User Input Agent
   - Receive agent response
   - If response contains `# Validated Input Report` → conversation done, go to step 6
   - Otherwise pass agent response → User Simulator → get next message → loop
6. Spin up a **Verification Agent** with the transcript, report, and criteria.
7. Report pass/fail results.

## Safety valve

Maximum **20 turns**. If the conversation has not produced a validated input report within 20 turns, the test fails with "conversation did not converge."

## Verification Agent input format

The Verification Agent receives:

1. **Conversation transcript** — interleaved messages in this format:
   ```
   User: <message>
   Agent: <message>
   [Tool call: tool_name(args)]
   [Tool result: ...]
   User: <next message>
   ...
   ```
2. **Final validated input report** — the Markdown content after `# Validated Input Report` in the agent's final message.
3. **Verification criteria** — the `## Verification Criteria` checklist from the scenario file.

A scenario passes only if **all** verification criteria pass. The Verification Agent reports each criterion individually with pass/fail and reasoning, plus an overall verdict.

## Scenario file structure

Each scenario follows this template:

- `## Setup` — data files and preconditions
- `## Scenario Description` — plain language context
- `## User Simulator` — persona, knowledge, behavior, opening message
- `## Verification Criteria` — pass/fail checklist

See the design spec at `docs/superpowers/specs/2026-03-23-thp-146-integration-tests-design.md` for full details.
