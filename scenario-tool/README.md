# Scenario Builder 0.1.0

Scenario Builder is an optional IFsCompanion tool, distributed separately as
`ifs-scenario-builder-0.1.0-win-x64.ifstool`. Companion 0.2.1 or newer is required.
Model Vetting is the only tool included by default in Companion.

In Companion, open Settings > Manage tools and install Scenario Builder from the
official catalog, or choose Add from file and select the `.ifstool` download.
Then open Scenario Builder from Tools. Uninstalling keeps the tool's saved data.

Select the IFs installation and configure the shared AI connection in Companion
Settings. The provider must support Chat Completions function tools. The tool
reads current shared settings for every request; it does not store a separate key.

Describe a new scenario or attach a UTF-8 `.sce` file up to 1 MB. Review the compact
proposal summary, optionally inspect a parameter/country/subgroup trajectory,
compare original and proposed inputs, or view the draft file before saving.
Global parameters have no country selector. The graph shows scenario input
values, not IFs forecast results.

Saving creates a distinct file under the tool's persistent data folder, in
`scenarios`. Existing files cannot be overwritten. Each generated file ends with
descriptive comments containing creation time, purpose, parameter names, model
context and a regeneration prompt. Comments do not duplicate the numeric arrays.
Original attachment comments are preserved. Chat and unsaved drafts are temporary.

Messages, relevant metadata and requested scenario rows are sent to the configured
AI provider. File parsing, validation and export run locally. Stop cancels the
pending proposal after the current provider call returns (up to its timeout).

To build from the repository, run the packaging Python with
`scenario-tool/build_tool.py`. The package includes its Python runtime and does
not require a separate Python installation. The executable is unsigned.
