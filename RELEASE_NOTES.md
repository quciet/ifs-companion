# IFsCompanion 0.2.0

Released October 20, 2026.

Scenario Builder is now included. Use one chat to create a scenario or attach an
existing UTF-8 `.sce` file to inspect and modify it. It uses the shared AI connection
in Settings and validates proposals against the selected IFs installation.

- Review a compact proposal summary and open the optional graph inspector to
  filter by parameter, country and subgroup. Global parameters have no country
  selector. For edits, compare original and proposed input trajectories.
- View the draft file before saving. Exports preserve the source file and include
  creation time, purpose, exact parameter names, model context and a descriptive
  regeneration prompt. Generated comments do not duplicate annual value arrays.
- Shared AI settings serve Scenario Builder and Code Interpreter. API keys are
  encrypted for the current Windows user. The provider must support Chat
  Completions function tools for Scenario Builder.
- Companion data defaults to a folder beside the application. Settings > Storage
  supports moving saved data to another dedicated folder with verified migration.
- Updated app branding and tool management, including richer release details.

The graph shows scenario parameter inputs, not model forecast results. Run IFs
to inspect resulting model outcomes. Attachments are limited to 1 MB and UTF-8;
chat sessions and unsaved drafts are cleared when Companion closes. Parameter
metadata and requested scenario rows are sent to the configured AI provider.

Choose the Windows x64 installer or portable ZIP. Model files and an IFs
installation are not included. The installer is unsigned; it includes the
WebView2 bootstrapper. Portable users need WebView2 installed. Existing settings
and saved work are preserved by updates. SHA256 checksums accompany both downloads.
