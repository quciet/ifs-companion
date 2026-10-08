# IFsCompanion

Windows desktop home for IFs tools, version 0.1.0. This project owns the shell,
Companion chat interface, shared Settings, Recent Work, desktop host, and installer.
The working comparison tool lives in the separate `ifs-model-vetting` repository.
IFs Autotune is an optional installable tool. AI, code reader, and scenario builder are not connected yet.

## Develop

Keep the two checkouts next to each other:

    ifs-companion/
    ifs-model-vetting/

Set `IFS_MODEL_VETTING_PATH` if the tool checkout is elsewhere. Install the pinned
dependencies from `packaging/requirements-build.txt` in a Python 3.14 environment.
Run `python companion_server.py` and visit http://127.0.0.1:8766 for UI development.
The tool decoder must have been built with `ifs-model-vetting/build.ps1` first.
Run `python -m unittest discover -s tests -v` for integration checks.

## Package

Run `./build.ps1 -PythonPath <python.exe>`. Optional `DotnetPath`, `InnoPath`, and
`ModelVettingPath` arguments override the local defaults. The build reads the tool
checkout, bundles its engine/UI, and produces one installer and portable ZIP in
`release`. Users do not need either source checkout or a separate tool installation.
Run `dist/IFsCompanion/IFsCompanion.exe` to preview without installing.

The small adapter is `companion_server.py`. It delegates comparison endpoints to
the tool's existing HTTP handler and serves the shared shell around its UI.
Optional tools use the small local package manager described in TOOL_PACKAGES.md.
The build uses the current tool checkout; coordinate incompatible changes in
the two projects and run integration tests before releasing.

Existing user settings/reports remain under `%LOCALAPPDATA%/IFsModelVetting` for
compatibility. `IFS_VETTING_DATA_DIR` overrides this for isolated tests.
Desktop smoke test: `IFsCompanion.exe --smoke-test <absolute-output.json>`.
The current installer is unsigned. No GitHub release is automatically published.

Release retention: after a successful build, build.ps1 verifies both packages against the SHA256 manifest and removes older installer/portable releases and checksum manifests from release/. Failed builds preserve prior releases. Source, installed applications, and user data are unaffected.

## Optional tools

Open Settings > Manage tools > Install from file and select a trusted `.ifstool`
package. Installed tools appear under Tools and open in Companion's right panel.
Use Close tool before Update from file or Uninstall. Stop active work inside the
tool first. Uninstall removes program files and preserves settings and results.
Closing Companion also closes optional tools; it asks first if a tool is busy.

Tool files live under `%LOCALAPPDATA%/IFsModelVetting/companion/tools` and user
data under the separate `companion/tool-data` directory. `IFS_VETTING_DATA_DIR`
redirects both for testing. Packages include their runtimes, so coworkers do not
need Python, Node, or source repositories. Manage tools reads the official catalog from this repository. Online installation
checks the release checksum and compatibility. Updates are user-triggered; local
Install from file remains available when offline.

For the optional autotune package, see the sibling `ifs-autotune` repository's
`scripts/build-tool.py`. Required small tools remain bundled with Companion.

## Official tool releases

The approval catalog is `official-tools/catalog.json`. Tool packages are GitHub
Release assets in this repository, not files committed to Git. See
`official-tools/README.md` for the publishing workflow. Companion's repository and
release downloads are public so installation does not require a GitHub account.
Compare Runs is the first published tool. It remains included with Companion;
its downloadable package enables independent updates and preserves existing reports.
