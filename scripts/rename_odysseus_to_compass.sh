#!/usr/bin/env bash
#
# Purpose: deterministically rename the tracked package directory from
# `odysseus/` to `compass/` and rewrite tracked text references.
# Idempotency: the directory rename step skips cleanly if `compass/` already
# exists and `odysseus/` no longer does; substitution only targets tracked
# files that still contain an Odysseus reference.
# How to run: from the repository root, execute
# `./scripts/rename_odysseus_to_compass.sh`.
# Substitution order matters: specific protocol/import/package-name rewrites
# must run before the final catch-all `odysseus -> compass` rule to avoid
# clobbering earlier targets.

set -euo pipefail

LC_ALL=C
export LC_ALL

FILES_MODIFIED=0

if sed --version >/dev/null 2>&1; then
  SED_INPLACE=(sed -i)
else
  SED_INPLACE=(sed -i '')
fi

rename_directory() {
  if [ -d "odysseus" ] && [ ! -e "compass" ]; then
    printf 'STEP 1: renaming directory with git mv: %s -> %s\n' "odysseus" "compass"
    git mv odysseus compass
    return
  fi

  if [ -d "compass" ] && [ ! -e "odysseus" ]; then
    printf 'STEP 1: directory rename already applied; skipping.\n'
    return
  fi

  printf 'ERROR: expected exactly one of %s/ or %s/ to exist before rename; found ambiguous state.\n' "odysseus" "compass" >&2
  exit 1
}

should_process_file() {
  case "$1" in
    docs/superpowers/*) return 1 ;;
    outputs/*) return 1 ;;
    uv.lock) return 1 ;;
    .git/*) return 1 ;;
    .worktrees/*) return 1 ;;
    scripts/rename_odysseus_to_compass.sh) return 1 ;;
  esac

  case "$1" in
    *.py|*.md|*.toml|*.yaml|*.yml|*.json|*.txt) return 0 ;;
    .gitignore) return 0 ;;
    CLAUDE.md) return 0 ;;
    README.md) return 0 ;;
    .claude/rules/generalize-merge-discipline.md) return 0 ;;
    .claude/rules/generalize-fix-routing.md) return 0 ;;
  esac

  return 1
}

substitute_in_tree() {
  local file
  local before_cksum
  local after_cksum

  printf 'STEP 2: applying ordered substitutions across tracked files.\n'

  while IFS= read -r file; do
    [ -n "$file" ] || continue

    if ! should_process_file "$file"; then
      continue
    fi

    if ! grep -qi 'odysseus' "$file"; then
      continue
    fi

    before_cksum=$(cksum < "$file")

    "${SED_INPLACE[@]}" \
      -e 's|odysseus://|compass://|g' \
      -e 's|odysseus_|compass_|g' \
      -e 's|from odysseus|from compass|g' \
      -e 's|import odysseus|import compass|g' \
      -e 's|python -m odysseus|python -m compass|g' \
      -e 's|uvx odysseus|uvx compass|g' \
      -e 's|name = "odysseus"|name = "compass"|g' \
      -e 's|"odysseus"|"compass"|g' \
      -e "s|'odysseus'|'compass'|g" \
      -e 's|Odysseus|Compass|g' \
      -e 's|ODYSSEUS|COMPASS|g' \
      -e 's|odysseus|compass|g' \
      "$file"

    after_cksum=$(cksum < "$file")
    if [ "$before_cksum" != "$after_cksum" ]; then
      FILES_MODIFIED=$((FILES_MODIFIED + 1))
    fi
  done <<EOF
$(git ls-files)
EOF
}

report() {
  local remaining

  printf 'Files modified: %s\n' "$FILES_MODIFIED"
  printf 'Post-run verification (`git grep -i -l odysseus` with exclusions):\n'

  remaining=$(
    git grep -i -l 'odysseus' -- \
      ':!docs/superpowers' \
      ':!outputs' \
      ':!uv.lock' \
      ':!scripts/rename_odysseus_to_compass.sh' || true
  )

  if [ -n "$remaining" ]; then
    printf '%s\n' "$remaining"
  else
    printf '(none)\n'
  fi
}

main() {
  local repo_root

  repo_root=$(git rev-parse --show-toplevel)
  cd "$repo_root"

  rename_directory
  substitute_in_tree
  report
}

main "$@"
