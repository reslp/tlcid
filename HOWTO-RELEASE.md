# Releases (GitHub Actions)

A release workflow is defined in `.github/workflows/release.yml`.

- **Trigger:** push that changes the `VERSION` file.
- **Branch guard:** jobs run only when that push is on the repository default branch.
- **Tag:** the workflow reads `VERSION` and creates/uses a git tag with that exact value.
- **Artifacts:** PyInstaller builds for Linux, macOS, and Windows are attached to the GitHub Release.
- **Release notes:** generated from commits since the previous tag; if no prior tag exists, full history is used.

## How to cut a release

1. Update `VERSION` with the new release value (for example `0.1.2`).
2. Commit and push that change to the default branch.
3. GitHub Actions will build all platforms, ensure the matching tag exists, and create/update the release.

