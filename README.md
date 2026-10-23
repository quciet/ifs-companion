# IFsCompanion

IFsCompanion is a Windows desktop workspace for working with International Futures (IFs). Compare model runs, inspect differences over time, and keep your saved comparisons and tools in one place.

## What you can do

- **Compare runs:** choose a baseline and comparison run, select shared variables, and examine differences.
- **Inspect results:** open result and audit rows to explore trajectories, then export CSV data or SVG charts.
- **Return to saved work:** reopen saved comparisons from Recent Work.
- **Manage tools:** install optional tools and check for tool updates from within the app.

Model Vetting is included and works without an AI connection or API key. Model Vetting is the only included tool. Scenario Builder is an optional `.ifstool` package: install it from Manage tools to create or modify scenarios using the shared AI connection. The source main chat supports persistent conversations and contextual tool review tabs; see [Chat workspace integration](CHAT_WORKSPACE.md) for capabilities, package requirements and remaining execution work. Code Interpreter can be installed from its separate `.ifstool` package. Configure the shared Chat Completions-compatible provider under Settings > AI connection. Autotune can be installed from the official catalog or a separate tool package.

## Download and install

Get the Windows installer or portable ZIP from [Releases](https://github.com/quciet/ifs-companion/releases).

**Requirements:** Windows 10 version 1809 or later, or Windows 11, on an x64 computer. You will also need your own IFs installation and model files; these are not included.

### Installer

1. Download and run the `IFsCompanion-Setup-…-win-x64.exe` installer.
2. Open IFsCompanion from the Start menu or desktop shortcut.

The installer includes the required application runtimes and installs Microsoft WebView2 if it is missing. Installing WebView2 requires an internet connection. The current installer is unsigned.

### Portable version

1. Download and extract the complete portable ZIP.
2. Open `IFsCompanion.exe` from the extracted folder.

Keep all extracted files and folders together. The portable version requires WebView2 to be installed already; use the installer if it is missing.

## Your first comparison

1. Open **Settings** and browse to your IFs installation folder, which contains `DATA` and `RUNFILES`. Select **Validate and save**. Companion requires `IFsInit.db` with a readable base year and model version; `DATA/IFsHistSeries.db`, `DATA/DataDict.db`, and `DATA/SAMBase.db`; `RUNFILES/IFsHistSeries.db`, `RUNFILES/DataDict.db`, `RUNFILES/IFsVar.db`, `RUNFILES/IFsBase.run.db`, and `RUNFILES/IFs.db`; and `net8/ifs.exe`. The detected version and base year appear in Settings.
2. Open **Tools > Model Vetting** and choose your baseline and comparison runs.
3. Load the shared variables, select the outputs you want to examine, and run the comparison.
4. Select a result or audit row to inspect trajectories. Export CSV data or SVG charts as needed.
5. Use **Recent Work** to return to saved comparisons.

Comparison work runs locally on your computer. The results provide numerical evidence to help you assess model changes; you decide whether those changes are expected.

## Add or update tools

Open **Settings > Manage tools** for one searchable list of installed and official tools. This screen manages tools; open installed tools from the left sidebar.

- Choose **Add from file** to install a trusted `.ifstool` package.
- For an available official tool, click **Install** directly in Manage tools. Use **+ → Install from file** for a downloaded `.ifstool` package. Scenario Builder requires Companion 0.2.1 or newer.
- Installed official tools offer **Update**, **Update from file**, and **Uninstall**. Update is enabled when a newer compatible official release is available.
- Unofficial tools offer **Update from file** and **Uninstall**.

The official catalog refreshes when you open this screen. File installs support explicitly selected older and prerelease versions. Only use trusted packages; older versions may not understand saved data from newer versions.

Uninstall closes an idle tool and removes it from the sidebar while preserving settings and saved work. Stop active work first. Removing the included comparison tool disables it; its bundled files remain part of Companion. Reinstall it from the official catalog or a package to use it again.

## Saved work and settings

Companion stores settings, results, optional tools, logs, browser data, and temporary files in `data` beside `IFsCompanion.exe` by default. This also applies to the portable ZIP. Install or extract Companion on the drive where you want this data to live.

Use **Settings > Storage** to choose a dedicated empty folder, then close and reopen Companion. The next launch copies and verifies saved data before switching. After the new location is saved, Companion automatically removes the verified originals. No permanent backup is created; the transfer temporarily needs room for both copies. If cleanup is interrupted or files are locked, Companion continues using the new folder, reports the incomplete cleanup in Settings, and retries on the next launch. Changed or unexpected files in the old folder are preserved. Browser cache and temporary files are rebuilt. Existing exports and explicitly selected Autotune output folders are not relocated.

On first launch with a new default data folder, earlier `%LOCALAPPDATA%\IFsModelVetting` data is imported using the same verified migration process. `storage.json` beside the executable records the location; the default is relative so a portable folder can move between drives. The application folder must be writable to save this setting. The advanced `IFS_VETTING_DATA_DIR` environment override takes precedence and disables location changes in Settings.

Updates and uninstall preserve data and `storage.json`. Windows-managed components such as the shared WebView2 runtime remain in Windows-managed locations. Tool packages run native code; Companion supplies storage and temporary paths, but cannot force third-party tools to honor them.

Closing Companion also closes optional tools. If a tool is busy, the app asks before interrupting it.

For more usage details, see the [User Guide](USER_GUIDE.txt).

## Feedback and license

Report problems or suggest improvements through [GitHub Issues](https://github.com/quciet/ifs-companion/issues).

IFsCompanion is available under the [MIT License](LICENSE). See [Third-party notices](THIRD_PARTY_NOTICES.txt) for bundled software acknowledgments.

## Optional Scenario Builder

Scenario Builder is distributed separately from Companion as a versioned
`.ifstool` download. It is not installed or bundled by default. Requires Companion
0.2.1 or newer. Open Settings > Manage tools, find Scenario Builder, and install
from the official catalog or choose Add from file. Then open it from Tools.

It reads the selected IFs installation and shared AI connection from Companion
Settings on each request. The provider must support Chat Completions function
tools. Use one chat to create a scenario or attach a UTF-8 `.sce` file up to 1 MB.
Inspect parameter/country/subgroup graphs, original versus proposed inputs, annual
values, and the draft file before saving a distinct file with descriptive comments.

Tool data and generated files live under the per-tool storage folder, separately
from program files. Uninstall preserves that data. See
[Scenario Builder usage](https://github.com/quciet/ifs-scenario-builder) for full details and the build
command. Only Model Vetting works without installing an optional tool.

## Update Companion

Open **Settings > Companion updates > Check for updates**. The app checks stable
Companion releases from the official GitHub repository, excluding optional-tool
releases and prereleases. Choose the installer or portable ZIP and click
**Download update**. Downloads are stored under `updates` in the active data
folder and checked against the release SHA256 manifest before they are offered.

For an installed copy, **Install update and close Companion** checks the package
again, waits for running work to finish, and launches the Windows installer in
the current application folder. Companion closes so its program files can be
updated. Settings, installed optional tools and saved work remain in the data
folder. This action does not install or update optional tools.

Portable users can save a copy of the verified ZIP, close Companion, and extract
it over their existing program files while preserving `data` and `storage.json`.
Source checkouts can download packages but cannot launch in-place installers.
No update check or download happens automatically. Offline checks show an error
rather than reporting that the app is up to date. Versions predating this update
feature need one manual app update before these controls become available.

### Shared Python (0.3.0+)

Companion and the new official tool packages use one private Python runtime. Optional libraries download automatically on first installation and are stored once across tools. Uninstall removes only libraries no remaining tool requires; saved work stays. A first file installation may also require internet access. Legacy self-contained packages still work and retain their own runtimes until replaced with a new package. See [Shared Python](SHARED_PYTHON.md) for packaging and development commands.

### Local build folders

- `release/` contains the current distributable installer, portable ZIP, and SHA256 manifest. Older releases are pruned only after the new packages pass verification.
- `build/package-<id>/IFsCompanion/` is temporary staging for current builds. Successful builds remove their staging folder. Failed builds may leave one for diagnosis.
- `dist/IFsCompanion/` is an existing runnable development/portable copy used by `start.ps1`. It can contain real saved work in `data/` and its storage selection in `storage.json`. Do not treat it as disposable build output. `build.ps1` creates immutable versioned releases. `start.ps1` verifies the newest local portable release and updates program files in this folder before launch, preserving data and storage.json. Close the running dist app before updating; use `start.ps1 -SyncOnly` to update without launching. Increment the application version before each changed release.
- `dist/IFsCompanionEngine/` was the separate PyInstaller engine output, later copied into the desktop package. Shared-Python builds no longer use it.
- `dist/ScenarioBuilder/` was standalone Scenario Builder packaging output. Scenario Builder now lives in the separate `ifs-scenario-builder` repository and uses shared-Python packaging.

The obsolete separate engine and Scenario Builder output copies and their PyInstaller work directories were removed during cleanup. The obsolete Scenario Builder standalone recipe has been retired. Build tools, shared-runtime development environments, test evidence, and saved user data are kept separately and should not be removed solely because they are old.

Temporary-file policy: builds now remove their own package staging in a finally block, including after failure. Test runs must use disposable per-run directories and clean up runtime/tool copies and browser caches after stopping their own processes. Keep concise diagnostic reports, not full extracted environments. Saved work and reusable development dependencies are excluded; see AGENTS.md.


### Cleanup after an app update

After the packaged desktop successfully loads, Companion verifies the installed
files against `app-files.json` before cleaning up. It removes old program files
only when the last successful installation recorded them and their checksums are
unchanged. Unknown files, modified files, settings, and the selected storage folder
are preserved. Locked files are retried on the next successful launch. This works
for both installer updates and portable/dist overlays.

Completed installer/ZIP downloads and recognized interrupted downloads under the
active storage folder's `updates/<version>/` are removed for the running version
and older versions. Newer downloads and unrelated files are retained. Manually
saved installers outside that managed folder are not deleted.

The first manifest-enabled launch establishes a baseline: old files from versions
that did not record ownership cannot be safely identified and are left intact.
Failed launches or incomplete/modified installations do not trigger cleanup.
The normal build generates the manifest; source checkouts do not run cleanup.
