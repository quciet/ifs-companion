# Scenario Builder 0.3.1

Fixes metadata-limit failures on scenarios with many parameters. Valid local
lookup batches no longer have an arbitrary operation count cap. Identical
lookups reuse cached results instead of rereading the metadata.

Repeated lookup cycles, the AI round-trip checkpoint, and provider interruptions
now pause research with **Continue researching** and **Revise request** actions.
The original request, attachment, and metadata results are preserved in the
current chat. A visible **Stop** action pauses after the current AI call returns;
Companion's Stop action also preserves progress.

Provider context is bounded without discarding the full local research history.
Country and parameter validation, stale-installation checks, and explicit
confirmation before creating a working draft remain in place.

Requires **IFsCompanion 0.3.0 or newer**. Update from **Manage tools**, or install
the downloaded `.ifstool` package from file. Existing saved scenarios are kept.
