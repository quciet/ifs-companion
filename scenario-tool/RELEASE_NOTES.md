# Scenario Builder 0.3.0

Regional scenario requests can now use preset country groups from the selected
IFs installation. The AI searches group names and aliases and inspects membership.
Ambiguous definitions require clarification. Preset membership expands locally;
custom lists are explicitly labeled and must use exact installed IFs countries.

Every proposed scenario now pauses for **Confirm and build draft** in chat.
Review the purpose, parameter names, and expandable country membership, or describe
a revision. Preview and export stay blocked until confirmation. Saving remains
a separate action. Revisions and installation changes invalidate stale approvals.

The chat distinguishes **You** in dark blue, right-aligned bubbles from
**Scenario Builder** in light, left-aligned cards. Both have explicit speaker labels.

The integrated composer includes a **+** attachment button, an attached-file chip,
and a send arrow. Drag one `.sce` onto the composer or choose a file without losing
your typed message. Enter sends; Shift+Enter inserts a line. Sending a newly
attached file alone requests an overview without proposed changes.

Requires **IFsCompanion 0.3.0 or newer** and uses its shared Python runtime, IFs
installation, and AI connection. Install or update from **Manage tools**, or
install the downloaded `.ifstool` package from file. Scenario Builder remains
optional. Existing saved scenarios are preserved.
