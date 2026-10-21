# Scenario Builder 0.3.3

Fixes duplicate scenario targets caused by overlapping country selections.
Identical annual trajectories for the same parameter and complete dimension
target merge into a single row. The confirmation reports how many identical
definitions were merged.

Conflicting trajectories now ask the user which definition should apply instead
of ending the conversation with a raw duplicate-target error. The original
request and proposed definitions stay in the chat for clarification.

Identical edits to attached scenarios apply once. Other overlapping adjustments
require clarification so multipliers are not accidentally applied twice.
Unrelated dimension targets and disjoint time intervals remain independent.

Requires **IFsCompanion 0.3.0 or newer**. Update from **Manage tools** or install
the downloaded `.ifstool` package. Existing saved scenarios are kept.
