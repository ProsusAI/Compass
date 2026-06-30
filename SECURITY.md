# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in Project Compass, please report it
**privately**. Do not open a public GitHub issue for security problems.

- Use [GitHub Private Vulnerability Reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)
  ("Report a vulnerability" under the repository's **Security** tab), or
- Contact the maintainers through the channel listed in the repository's
  contact information.

Please include:

- A description of the vulnerability and its potential impact.
- Steps to reproduce, or a proof of concept.
- Affected version(s) or commit SHA.

## Response

We aim to acknowledge new reports within **5 business days** and to provide an
initial assessment within **10 business days**. We will keep you informed of
remediation progress and coordinate disclosure timing with you.

## Scope

This project is an MCP server that orchestrates LLM calls. When reporting,
note that it relies on third-party LLM provider APIs and on API keys supplied
via environment variables (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`). Never
include real API keys, credentials, or proprietary data in a report.

## Supported Versions

Security fixes are applied to the latest released version on the default
branch. Older versions are not maintained unless otherwise stated.
