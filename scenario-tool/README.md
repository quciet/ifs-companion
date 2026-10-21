# Scenario Builder 0.4.0

Scenario Builder is an optional IFsCompanion tool, distributed separately as
`ifs-scenario-builder-0.4.0-win-x64.ifstool`. Companion 0.3.0 or newer is required.
Model Vetting is the only tool included by default in Companion.

In Companion, open Settings > Manage tools and install Scenario Builder from the
official catalog, or choose Add from file and select the `.ifstool` download.
Then open Scenario Builder from Tools. Uninstalling keeps the tool's saved data.

Select the IFs installation and configure the shared AI connection in Companion
Settings. The provider must support Chat Completions function tools. The tool
reads current shared settings for every request; it does not store a separate key.

Describe a new scenario or attach a UTF-8 `.sce` file up to 1 MB. Review the compact
chat composer: use **+** or drop one `.sce` onto the input, then send with the arrow
or Enter. Shift+Enter adds a line. Attachments appear inside the composer and keep
your typed message; they are sent to the AI only when you send. Sending a newly
attached file without a message requests an overview without proposed changes.
Replacing or removing a source after a conversation starts requires confirmation
and clears that conversation; your typed message is kept.

Review the
confirmation in chat and approve **Confirm and build draft**, or describe a revision.
No draft can be previewed or exported before this explicit confirmation.
For regional requests the AI searches `DATA/IFs.db` preset groups and aliases,
then reads their membership. Ambiguous definitions require clarification. Selected
presets expand locally into exact IFs countries; `IFS.grp` remains the separate
parameter dimension index. If no preset fits, a custom list must use exact installed
country names and is labeled as custom in the confirmation. Expand the country
membership details to inspect the full list. Changes to the installation or a new
chat message invalidate the previous confirmation.

After confirmation, review the compact
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
`scenario-tool/build_tool.py --version 0.4.0`. The package uses Companion's shared
Python runtime; users do not need a separate Python installation.

Research supports large local metadata batches without a parameter lookup count
cap. Identical lookups are cached within the chat. Repeated cycles without new
metadata, the AI round-trip checkpoint, and connection interruptions pause with
**Continue researching** and **Revise request** actions. Both preserve the original
request, attached source, and lookup results. **Stop** pauses research after the
current provider call returns. Old metadata exchanges can be omitted from the
provider context to keep it bounded; the full transcript and results remain local
and are available through the metadata tools. Progress is in memory for the current
chat and does not survive restarting the tool. Parameter/country validation and
explicit confirmation before preview/export remain mandatory.

Empty or incorrectly formatted AI answers receive one format-only retry. If the
provider still cannot supply a valid response, research pauses with progress
preserved instead of showing a JSON parser error. No values or dimensions are
inferred during response recovery.

Identical trajectories from overlapping country selections merge into one row,
with a merge count in the confirmation. Conflicting trajectories or overlapping
attachment edits prompt a clarification instead of silently overwriting or
compounding the changes. Research and the original request stay in the chat.


Version 0.4.0 reads parameter explanations, units, bounds, shift-up/down settings,
shift durations and aggregation/common-target flags from the selected installation.
Its high/low/base tool reads actual country/dimension values from
`RUNFILES/IFsBase.run.db` using Companion's bundled baseline decoder, read-only.
High and low are numerical input shifts, not universal severity settings. Missing
payloads or defaults require clarification; they are not replaced with assumed
zeros, ones or invented moderate presets. Base retains saved baseline values.

Audited control rules check declared outcome direction against saved baseline
inputs and conservative explicit phrases in the user's narrative. Corruption
perception has inverse polarity. Nuclear additions must specify annual versus
cumulative quantities; cumulative additional-stock paths are converted to annual
increments, with zero further additions once the stock target is held. Rules do
not guarantee model outcomes. Controls without an audited outcome polarity are
marked as requiring review. The confirmation shows interpretations and preset
calculations. Baseline or metadata changes invalidate pending reviews.

Exports use exact native IFs group names when uniform inputs and saved baseline
values make the AVG/POP group transform equivalent. Country-specific inputs,
unequal baselines, SUM allocation and common-target behavior retain explicit
country records, with the reason shown. Native group files written this way can
be reopened and expanded for editing/inspection. Other native group allocation
semantics require explicit resolution before editing; they are never silently
flattened. ALL subgroup selectors resolve to real indices before baseline lookup.

World at War checks include the reversed-corruption case, all existing nuclear
states identified from positive baseline GOVNUCWP, seven additional states,
cumulative nuclear additions and native World/PRB Africa records. Monadic
migration is explicitly labeled as an approximation rather than an exact
Africa-to-Africa route constraint. Labour/spending controls do not guarantee
military headcounts. These checks do not solve an IFs forecast.
