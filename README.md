# IFsCompanion

IFsCompanion is a Windows desktop workspace for working with International Futures (IFs). Compare model runs, inspect differences over time, and keep your saved comparisons and tools in one place.

## What you can do

- **Compare runs:** choose a baseline and comparison run, select shared variables, and examine differences.
- **Inspect results:** open result and audit rows to explore trajectories, then export CSV data or SVG charts.
- **Return to saved work:** reopen saved comparisons from Recent Work.
- **Manage tools:** install optional tools and check for tool updates from within the app.

Compare Runs is included and works without an AI connection or API key. AI assistance, Explore Code, and Create Scenario are not available yet. IFs Autotune can be installed from a separate tool package; online installation is coming soon.

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

1. Open **Settings** and browse to your IFs installation folder, which contains `DATA` and `RUNFILES`. Select **Validate and save**.
2. Open **Tools > Compare Runs** and choose your baseline and comparison runs.
3. Load the shared variables, select the outputs you want to examine, and run the comparison.
4. Select a result or audit row to inspect trajectories. Export CSV data or SVG charts as needed.
5. Use **Recent Work** to return to saved comparisons.

Comparison work runs locally on your computer. The results provide numerical evidence to help you assess model changes; you decide whether those changes are expected.

## Add or update tools

Open **Settings > Manage tools** to see official tools and available versions. Select **Install** for an available tool, or **Check for updates** to refresh the list. Online installation requires internet access but does not require a GitHub account.

You can also select **Install from file** and choose a trusted `.ifstool` package saved on your computer. This option works offline. Tool packages include their required runtimes.

Before updating or uninstalling a tool, stop its active work and select **Close tool**. Updates are started by you and are not installed automatically. Uninstalling a tool preserves its settings and saved work. Compare Runs remains included with Companion; removing its separate update package restores the included version.

## Saved work and settings

Settings, results, and logs are stored in `%LOCALAPPDATA%\IFsModelVetting`, retaining compatibility with earlier versions. Application updates and uninstall preserve this data.

Closing Companion also closes optional tools. If a tool is busy, the app asks before interrupting it.

For more usage details, see the [User Guide](USER_GUIDE.txt).

## Feedback and license

Report problems or suggest improvements through [GitHub Issues](https://github.com/quciet/ifs-companion/issues).

IFsCompanion is available under the [MIT License](LICENSE). See [Third-party notices](THIRD_PARTY_NOTICES.txt) for bundled software acknowledgments.
