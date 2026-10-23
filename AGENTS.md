# Release rules

- After publishing a successful new local build, keep only the current version's installer, portable ZIP, and checksum manifest in `release/`.
- Validate that both new packages exist, are nonempty, and match their SHA256 manifest before removing older release artifacts. Failed builds or verification must preserve prior releases.
- Use `packaging/prune-releases.ps1`, which is called by `build.ps1`. Restrict cleanup to recognized release filenames directly inside the release directory.
- Do not delete source, installed applications, settings, model files, or user results as part of release cleanup.
- This rule covers local build artifacts. Publishing or deleting remote releases requires authorization for that destination.

## Temporary build and test files

- Each build/test owns a unique temporary directory. Use Python TemporaryDirectory or a PowerShell try/finally cleanup block; stop owned processes and close files before cleanup, including after failures.
- Delete disposable extracted app copies, copied tool installations, browser profiles, download caches, and staging runtimes at the end of the run. Retain only concise logs, test summaries, and useful screenshots under output/.
- Do not retain whole test environments as evidence. If debugging requires one, explicitly record its purpose and remove it when the issue is resolved.
- Never sweep output/, build/, or dist/ wholesale. Inspect exact targets, resolve them beneath this workspace, reject filesystem links, and check active processes first. Preserve settings, scenarios, saved comparisons, tool-data, and unknown user-created files.
- dist/IFsCompanion and its configured data location are user workspaces, not temporary directories. Do not touch them during cleanup.
- Keep the reusable build/shared-dev runtime, build/test-support dependencies, .packaging-venv314, decoder-runtime, and build tools unless their consumers have been retired.
- Before completing build/test work, remove its disposable artifacts and report any intentional retained environment. Never stop another task's app, tests, or publishing process to clean up.
