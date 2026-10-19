#!/usr/bin/env bash
# Print the description of a release pull request: what is released, the commits
# since the last tag, and what to check before merging.
#
# Usage: scripts/release-pr-body.sh VERSION   (run on main, before the version bump)
set -euo pipefail

version="$1"
previous=$(git describe --tags --abbrev=0 --match 'v*' 2> /dev/null || true)

echo "Release v$version${previous:+ (after $previous)}. Unless a version was given when"
echo "the workflow ran, commitizen picked it from the conventional commits below."
echo
echo "### Commits since ${previous:-the start}"
echo
git log --no-merges --pretty='- %s' "${previous:+$previous..}HEAD"
echo
echo "### Before merging"
echo
echo "- Read the new section of \`CHANGELOG.md\` and edit it on this branch if needed."
echo "- To release another version, change it in \`pyproject.toml\`, \`uv.lock\` and the"
echo "  changelog heading. The release check on this pull request verifies they agree."
echo
echo "### After merging"
echo
echo "The Release workflow builds the package and waits for you to approve the \`pypi\`"
echo "environment. After approval it publishes to PyPI, then tags the commit and creates"
echo "the GitHub release with the changelog section."
