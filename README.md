# IFsCompanion

Windows desktop home for IFs tools, version 0.1.0. This project owns the shell,
Companion chat interface, shared Settings, Recent Work, desktop host, and installer.
The working comparison tool lives in the separate `ifs-model-vetting` repository.
AI and the other tools are not connected yet.

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
There is deliberately no plugin loader or separate dependency framework yet.
The build uses the current tool checkout; coordinate incompatible changes in
the two projects and run integration tests before releasing.

Existing user settings/reports remain under `%LOCALAPPDATA%/IFsModelVetting` for
compatibility. `IFS_VETTING_DATA_DIR` overrides this for isolated tests.
Desktop smoke test: `IFsCompanion.exe --smoke-test <absolute-output.json>`.
The current installer is unsigned. No GitHub release is automatically published.
