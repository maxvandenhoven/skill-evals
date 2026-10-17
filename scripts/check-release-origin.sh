#!/usr/bin/env bash
# Succeed only if the commit being released came from a release pull request that the
# Prepare release workflow opened: merged into main, from a release/v* branch of this
# repository, authored by the release bot. Anyone else's pull request, including one
# that only changes the version, does not make a release.
#
# Usage: GH_TOKEN=... RELEASE_BOT=<bot login> scripts/check-release-origin.sh SHA
set -euo pipefail

sha="$1"
bot="${RELEASE_BOT:-}"

if [ -z "$bot" ]; then
    echo "RELEASE_BOT_LOGIN is not set, so nothing can be released." >&2
    exit 1
fi

count=$(
    gh api "repos/$GITHUB_REPOSITORY/commits/$sha/pulls" | jq \
        --arg bot "$bot" --arg repo "$GITHUB_REPOSITORY" '
        [.[] | select(
            .merged_at != null
            and .base.ref == "main"
            and (.head.ref | startswith("release/v"))
            and .head.repo.full_name == $repo
            and .user.login == $bot
            and .user.type == "Bot"
        )] | length'
)

if [ "$count" -lt 1 ]; then
    echo "Commit $sha did not come from a release pull request opened by $bot." >&2
    exit 1
fi
