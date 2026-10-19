#!/usr/bin/env bash
# Prepare the files of a release: a branch release/vX.Y.Z from an up-to-date main, with
# the version in pyproject.toml and uv.lock bumped and CHANGELOG.md updated from the
# conventional commits since the last tag. Nothing is committed, pushed or tagged. The
# Prepare release workflow runs this, then commits and opens the pull request.
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
    if [ -z "$manual" ] && ! version=$(uv run cz bump --get-next --yes 2> /dev/null); then
        echo "No feat, fix, perf or refactor commits since the last tag, so there is" >&2
        echo "nothing to release. To release anyway, give a version." >&2
        exit 1
    fi
    version="${manual:-$version}"
    git switch -c "release/v$version"
    uv run cz bump --files-only --changelog --yes ${manual:+"$manual"}
fi

echo "Prepared release/v$version."
