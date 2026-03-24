# Routing Prompt Store

This directory is the versioned routing prompt store for the Odysseus pipeline. It is **currently empty** — routing prompts are created during pipeline runs, not checked in.

> Agent system prompts live in `odysseus/agents/prompts/`, not here.

## Versioning

Each file's **stem** (filename without extension) is the version name. For example, `v2.yaml` has version `"v2"`.

Requesting version `"latest"` resolves to the most recently modified prompt file in this directory.

When multiple files share the same stem (different extensions), the extension with the highest priority wins (see below).

## Supported File Formats

Extensions are recognized in the following priority order:

| Priority | Extension |
|----------|-----------|
| 1 | `.yaml` |
| 2 | `.yml` |
| 3 | `.txt` |
| 4 | `.md` |

YAML and plain text (`.txt`) are the primary formats used by the pipeline.

## How Prompts Are Loaded

`FilePromptManager` (in `odysseus/prompts/manager.py`) manages this directory:

- **Scanning** — On startup it scans the directory, reads all recognized files, and caches their contents.
- **Loading** — `load(version)` returns the cached text for the given version name, or raises `FileNotFoundError` if not found.
- **Hot-reload** — `watch()` is a long-running async coroutine (run as a background task) that rescans the directory whenever a file change is detected, keeping the cache current without a restart.

## Configuration

The prompts directory is configured via the `prompts_dir` constructor parameter when instantiating `FilePromptManager`:

```python
manager = FilePromptManager(prompts_dir="prompts/")
```

There is no environment variable override — the caller is responsible for supplying the path.
