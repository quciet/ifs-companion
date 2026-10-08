# Release rules

- After publishing a successful new local build, keep only the current version's installer, portable ZIP, and checksum manifest in `release/`.
- Validate that both new packages exist, are nonempty, and match their SHA256 manifest before removing older release artifacts. Failed builds or verification must preserve prior releases.
- Use `packaging/prune-releases.ps1`, which is called by `build.ps1`. Restrict cleanup to recognized release filenames directly inside the release directory.
- Do not delete source, installed applications, settings, model files, or user results as part of release cleanup.
- This rule covers local build artifacts. Publishing or deleting remote releases requires authorization for that destination.
