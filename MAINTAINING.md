# Maintaining

Notes for the maintainer: how releases work and which repository settings they rely on.

## Releasing

Contributors open pull requests with a conventional title (`feat: ...`, `fix: ...`),
and each is squash merged into `main`. A release is then two steps, both on GitHub.

**1. Open the release pull request.** In the Actions tab, run the Prepare release
workflow on `main`. Leave the version empty to take the one commitizen suggests from
the commits since the last tag (`feat` is a minor bump, `fix`, `perf` and `refactor`
are patch bumps), or type a version such as `0.2.0`. The workflow opens a pull request
titled `chore: release vX.Y.Z` with the version in `pyproject.toml` and `uv.lock`, the
new section in `CHANGELOG.md`, and a description that lists the commits. Only admins
and maintainers can run it, only from `main`, and it stops if a release pull request
is already open or there is nothing to release. When nothing qualifies for a bump but
you want a patch release anyway, give the version.

**2. Review and merge it.** Read the changelog section and edit it on the branch if you
like. To release a different version, change it in `pyproject.toml`, `uv.lock` and the
changelog heading; the check on the pull request fails if they disagree, if the
section is empty, or if the version is not higher than every tag. Squash merge it.

The Release workflow then runs on `main`. It publishes only if the version has no tag
yet and the commit came from a pull request that the Prepare release workflow opened,
which it recognises by its author, its `release/v*` branch and its merge into `main`.
Any other change to the version, such as an ordinary pull request that edits
`pyproject.toml`, only produces a warning in the run. The workflow builds the package,
smoke-tests the wheel, and waits for you to approve the `pypi` environment. After
approval it publishes to PyPI, then tags the commit and creates the GitHub release
with that version's changelog section. It cannot be started by hand.

If a run fails after the upload to PyPI, re-run its failed jobs. If PyPI has a bad
version, release a new patch version, as PyPI never reuses a version number.

The first release has no tag to bump from, so only the changelog is written and the
version stays as it is in `pyproject.toml`. `scripts/release-prepare.sh` is what the
workflow runs, and it works locally for debugging, but a release pull request opened
any other way is not published.

## The README on PyPI

The README is also the PyPI description of each release, and PyPI does not resolve
relative paths. Link images and files with absolute `https://github.com/...` or
`https://raw.githubusercontent.com/...` URLs. PyPI drops `<source>` tags, so a
`<picture>` shows its `<img>`, which is why that one is the light logo. The description
is fixed per release, so a README change shows on PyPI after the next release. Check
it with `uv build` and `uvx twine check dist/*`.

## Settings the workflows rely on

- A GitHub App, which opens the release pull request. A pull request opened with the
  built-in token does not start the CI checks that `main` requires. Create the app
  under Settings, Developer settings, GitHub Apps, with no webhook and the repository
  permissions Contents and Pull requests set to read and write. Install it on this
  repository only and generate a private key.
- Repository variable `RELEASE_APP_CLIENT_ID`: the app's client ID.
- Repository variable `RELEASE_BOT_LOGIN`: the app's bot user, such as
  `skill-evals-release[bot]`. The Release workflow publishes only commits from pull
  requests by this author.
- Environment `release`, limited to the `main` branch, with the secret
  `RELEASE_APP_PRIVATE_KEY` (the key's contents). Runs from other branches cannot read
  it.
- Environment `pypi`: you as required reviewer, with "prevent self-review" off, limited
  to the `main` branch.
- A trusted publisher on PyPI, for owner `maxvandenhoven`, repository `skill-evals`,
  workflow `release.yml` and environment `pypi`.
- Ruleset `protect-main`: pull requests with one approval, squash merges only, and the
  CI checks required. Admins can bypass the approval. The app opens the release pull
  request, so you can approve it yourself.
- Ruleset `protect-gh-pages`: no deletion or force-push.
