# IFsCompanion

IFsCompanion is a Windows desktop workspace for working with International Futures (IFs). Compare model runs, inspect differences over time, and keep your saved comparisons and tools in one place.

## What you can do

- **Compare runs:** choose a baseline and comparison run, select shared variables, and examine differences.
- **Inspect results:** open result and audit rows to explore trajectories, then export CSV data or SVG charts.
- **Return to saved work:** reopen saved comparisons from Recent Work.
- **Manage tools:** install optional tools and check for tool updates from within the app.

Model Vetting is included and works without an AI connection or API key. Scenario Builder is included: describe a new scenario or attach a UTF-8 `.sce` file, review proposed changes, and save a new file with descriptive comments. It uses the shared AI connection in Settings. The main Companion chat remains guided. Code Interpreter can be installed from its separate `.ifstool` package. Configure the shared Chat Completions-compatible provider under Settings > AI connection. Autotune can be installed from a separate tool package; online installation is coming soon.

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
- For an available official tool, open **+** and choose **Install** or **Install from file**.
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

## Scenario Builder

Open **Tools > Scenario Builder**. Select the IFs installation and configure the
shared AI connection in Settings first. The provider must support Chat Completions
function tools. Parameter names, dimensions, subgroup indices, country spellings,
model version and base year come from the selected installation.

Use the same chat to create scenarios, inspect attached scenarios, or request
changes. **Attach .sce** selects a local UTF-8 file up to 1 MB; replacing or removing
it clears the conversation and unsaved draft. Relevant rows and metadata are sent
to the configured AI provider only when you send a message. Original files are
not modified. Chat and draft state are temporary and cleared on restart.

Review the compact proposal summary in the full-width conversation. Open
**Inspect scenario** for a parameter and country/subgroup filtered graph of annual
scenario input values. Global parameters disable the country selector. For edits,
the graph overlays original and proposed values and lists only changed trajectories.
Annual tables are created on demand for the current selection. **View draft file**
opens the exact CSV-formatted draft with descriptive comments without saving; its
creation timestamp is finalized on export. The source attachment also has a
**View file** action. New input invalidates the previous draft;
changing the IFs installation requires a fresh chat. Click **Save reviewed .sce**
to save under `scenarios` in the active Companion data folder, then download a
copy if desired. Existing filenames are never overwritten. The generated comment
section includes creation time, purpose, exact parameter names, model context and
a descriptive regeneration prompt. It contains no generated structured
specification or duplicate annual value array. Existing source comments remain.

Supported plans include explicit annual trajectories, linear ramps with optional
holds, and changes by multiplication, addition, zeroing or a linear replacement
over an existing interval. The local compiler validates every accepted proposal;
AI text is never executed as code. AI requests can take several minutes when
multiple metadata lookups are needed. Provider failures never export a file.
