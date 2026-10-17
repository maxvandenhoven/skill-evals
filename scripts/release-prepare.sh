#!/usr/bin/env bash
# Prepare a release PR: a branch release/vX.Y.Z from an up-to-date main, with the
# version in pyproject.toml and uv.lock bumped and CHANGELOG.md updated from the
# conventional commits since the last tag. Nothing is committed or tagged: edit
# CHANGELOG.md by hand, commit, and open the PR. See MAINTAINING.md.
#
# Usage: scripts/release-prepare.sh [VERSION]   (default: the version commitizen picks)
set -euo pipefail

manual="${1:-}"

if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "Commit or stash your changes first." >&2
    exit 1
fi

git switch main
git pull --ff-only

if ! git tag --list 'v*' | grep -q .; then
    # First release: pyproject.toml already holds the version, so there is nothing
    # to bump. Only write the changelog.
    version="${manual:-$(uv version --short)}"
    git switch -c "release/v$version"
    uv run cz changelog --unreleased-version "v$version"
else
    version="${manual:-$(uv run cz bump --get-next --yes)}"
    git switch -c "release/v$version"
    uv run cz bump --files-only --changelog --yes ${manual:+"$manual"}
fi

echo
echo "Prepared release/v$version. Edit CHANGELOG.md, then commit and open a pull request."
