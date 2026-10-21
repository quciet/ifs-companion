# Scenario Builder 0.4.0

- Adds installed IFs parameter explanations, units, bounds, affected-variable
  definitions and audited semantic direction checks. Reversed corruption
  interventions are blocked for clarification. Unknown outcome polarity is
  explicitly marked for review rather than inferred.
- Adds IFs high/low/base suggestions calculated from actual country/dimension
  baseline values in IFsBase.run.db. Uses supplied shifts, durations and bounds;
  missing baseline values or presets are not invented. Base preserves the saved
  trajectory. The selected installation and its baseline are read-only.
- Writes native IFs country-group targets where baseline and aggregation checks
  establish equivalence. Preserves explicit country rows for differentiated
  inputs, unequal baselines, SUM allocation or common-target semantics. Shows the
  reason and expands supported native group records when reopening a file.
- Distinguishes cumulative nuclear stock additions from annual additions and
  converts cumulative trajectories to yearly increments. Reads existing nuclear
  states from the saved GOVNUCWP baseline. Discloses military-personnel proxies
  and the route limitations of country-level migration controls.
- Shows semantic interpretations, preset calculations and group-writing decisions
  in the confirmation. A changed baseline or metadata invalidates pending review.

Requires **IFsCompanion 0.3.0 or newer**, including its bundled baseline decoder.
No separate runtime is shipped with the tool. Update through **Manage tools** or
install the `.ifstool` package from file. Existing saved scenarios are preserved.

Validation uses installed IFs 8.74 metadata and baseline with the World at War
narrative. These are input/compiler checks, not a solved forecast or a guarantee
that every narrative interpretation is correct.
