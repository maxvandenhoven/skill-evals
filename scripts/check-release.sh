#!/usr/bin/env bash
# Check that the version in pyproject.toml is ready to release: uv.lock agrees with
# it, CHANGELOG.md has a filled section for it, it has no tag yet, and it is higher
# than every existing tag. Run on release pull requests and again before publishing.
#
# Usage: scripts/check-release.sh
set -euo pipefail

version=$(uv version --short)

fail() {
    echo "Release check failed: $*" >&2
    exit 1
}

git fetch --tags --force --quiet

if git rev-parse -q --verify "refs/tags/v$version" > /dev/null; then
    fail "tag v$version already exists."
fi

uv lock --check > /dev/null 2>&1 \
    || fail "uv.lock does not match pyproject.toml; run 'uv lock'."

if [ -z "$(scripts/changelog-section.sh "$version" | tr -d '[:space:]')" ]; then
    fail "CHANGELOG.md has no entries under '## v$version'."
fi

uv run --no-project --with packaging python -I - "$version" <<'PY' || exit 1
import subprocess
import sys

from packaging.version import Version

new = Version(sys.argv[1])
tags = subprocess.run(
    ["git", "tag", "--list", "v*"], capture_output=True, text=True, check=True
).stdout.split()
latest = max((Version(tag.removeprefix("v")) for tag in tags), default=None)
if latest is not None and new <= latest:
    print(f"Release check failed: {new} is not higher than v{latest}.", file=sys.stderr)
    sys.exit(1)
PY

echo "Release v$version is consistent."
