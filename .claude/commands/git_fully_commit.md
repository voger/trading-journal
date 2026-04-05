# git_fully_commit

Commit all changes to main and push to origin with changelog and optional version bump.

## Steps

1. **Check for changes**
   Run `git status` and `git diff`. If there is nothing to commit (clean tree, no untracked files), tell the user and stop.

2. **Ask about version bump**
   Ask the user: "Should I bump the version number? If yes — major, minor, or patch? Current version is in `build_installer_windows.nsi` (`!define VERSION`)."
   - Read the current version from `build_installer_windows.nsi`.
   - If the user wants a bump, calculate the new version (semver: major.minor.patch) and update **all** version references:
     - `build_installer_windows.nsi` — `!define VERSION`
     - `CHANGELOG.md` — add a new `## [X.Y.Z] — YYYY-MM-DD` section header (today's date)
   - If no bump, just add entries under the existing latest version section in `CHANGELOG.md`.

3. **Update CHANGELOG.md**
   - Read `git diff --staged` and `git diff` (unstaged) to understand what changed.
   - Also read `git log main..HEAD --oneline` to catch any unpushed commits.
   - Write a concise, accurate changelog entry under the appropriate version section, following the existing style (### Added / ### Fixed / ### Changed / ### Chore).
   - Do not invent items — only document what actually changed.

4. **Stage and commit**
   - Stage all changed files: use `git add` on specific files (never `git add -A` or `git add .` blindly — check `git status` and add what's appropriate).
   - Commit with a short, descriptive message following the repo's conventional commit style (e.g. `feat:`, `fix:`, `chore:`).
   - Append `Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>` to the commit message.

5. **Push**
   - Run `git push origin main`.
   - Use `gh` CLI for any GitHub operations (tags, releases, PRs) if needed.

6. **Report**
   - Tell the user what was committed, what version (if bumped), and confirm the push succeeded.
