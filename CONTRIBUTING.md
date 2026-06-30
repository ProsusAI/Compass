# Contributing to Project Compass

Thank you for your interest in contributing. This document explains how to
contribute and the intellectual-property terms that apply to contributions.

## Licensing & IP Assignment of Contributions

Project Compass is released under the [Apache License, Version 2.0](LICENSE).

By submitting a contribution (a pull request, patch, or any other work) to this
project, you agree that:

1. **License grant.** Your contribution is provided under the terms of the
   Apache License, Version 2.0, including the patent grant in Section 3 of that
   license.
2. **Original work / right to submit.** The contribution is your original
   creation and you have the right to submit it under the Apache-2.0 license. If
   your employer has rights to intellectual property you create, you represent
   that you have received permission to make the contribution on behalf of that
   employer, or that the employer has waived such rights.
3. **IP assignment.** To the extent permitted by applicable law, you assign to
   **MIH AI B.V.** the rights necessary to relicense and distribute your
   contribution as part of this project. Where assignment is not possible, you
   grant MIH AI B.V. a perpetual, worldwide, non-exclusive, royalty-free,
   irrevocable license to use, reproduce, modify, distribute, and sublicense the
   contribution.
4. **No confidential or proprietary material.** You will not include secrets,
   credentials, customer data, personal data (PII), or any third-party
   proprietary or confidential information in your contribution.

Contributors who are contractors or who contribute on behalf of an organization
must ensure an appropriate IP-assignment agreement is in place before
contributing. If you are unsure, contact the maintainers before opening a pull
request.

> A formal Contributor License Agreement (CLA) may be required for external
> contributions. The maintainers will provide the CLA process where applicable.

## Development Setup

```bash
git clone https://github.com/<org>/Compass.git
cd project-compass
uv sync
```

This project uses [`uv`](https://docs.astral.sh/uv/) for all dependency and
environment management — do not use `pip` directly.

## Before You Open a Pull Request

Run the full local check suite and make sure it passes:

```bash
uv run pytest          # tests
uv run ruff check .    # lint
uv run ruff format .   # format
uv run pyright         # type check
```

- Keep changes focused; one logical change per pull request.
- Update relevant documentation (`docs/`, module `README`s) in the same change
  when you alter agent prompts, the MCP surface, shared models, or cross-module
  interfaces.
- Add or update tests for new behavior.
- New source files must carry the Apache-2.0 header (see existing `.py` files).

## Reporting Bugs & Requesting Features

Open a GitHub issue with a clear description and reproduction steps. For
security issues, follow [SECURITY.md](SECURITY.md) instead — do not file a
public issue.

## Code of Conduct

Be respectful and constructive. Maintainers may remove contributions or
contributors that violate community standards.
