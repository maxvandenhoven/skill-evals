#!/usr/bin/env bash
# Print the body of a version's section in CHANGELOG.md (without its heading).
#
# Usage: scripts/changelog-section.sh VERSION   (without the leading v)
set -euo pipefail

awk -v v="v$1" '/^## /{p=($2==v); next} p' CHANGELOG.md
