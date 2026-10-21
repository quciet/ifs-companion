# Scenario Builder 0.3.2

Fixes the raw JSON parsing error ("Expecting value: line 1 column 1") when an AI
provider returns an empty answer or ordinary prose instead of the required JSON.
The builder now retries once with a format-only correction. It explicitly asks
for clarification when assumptions are missing and prohibits invented values,
parameters or country memberships.

If the provider still returns invalid response formatting, research pauses with
**Continue researching** and **Revise request**. The original request, attachment
and completed metadata lookups are preserved in the current chat. Proposal
validation and explicit confirmation remain mandatory.

Requires **IFsCompanion 0.3.0 or newer**. Update from **Manage tools** or install
the downloaded `.ifstool` package from file. Existing saved scenarios are kept.
