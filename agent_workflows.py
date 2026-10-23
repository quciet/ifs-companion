"""Focused instructions shared by all assistant sessions, separate from engines."""
WORKFLOWS = {
    'explain': '''Investigate IFs relationships using shared source/wiki evidence. Start with
search, then read relevant code or wiki sections. Cite exact returned paths, ranges and revision
identities. Distinguish implemented equations from inferred effects. Do not infer compatibility
between a bundled source revision and the selected installation without evidence.''',
    'scenario': '''Use shared IFs knowledge to clarify policy mechanisms when necessary.
Use the scenario operation for installed parameters, country scope, annual trajectories and
validated proposals. Pass agreed assumptions faithfully. Its review tab supplies existing graphs,
file preview, user confirmation and export. Revisions require a new proposal and approval.
Do not approve on the user's behalf. Use run_scenario to prepare execution approval of the exact
confirmed file and horizon. The review tab starts the run only after the user clicks Approve and run.
Use jobs/job to read progress. After completion use the saved output path for comparison; clarify
indicators when missing. A completed job can be reopened without rerunning the model.''',
    'comparison': '''Resolve exact run paths from installation and indicator codes from metadata.
Clarify ambiguous run names and economic-indicator scope. Propose a comparison through the
comparison operation, which opens existing Model Vetting with inputs filled. The user reviews
and starts it there. Completed report links refer to saved results; never rerun merely to view.''',
    'autotune': '''Clarify the tuning objective, parameters, bounds and metric. Open the existing
Autotune interface for configuration and execution. Do not invent configuration or claim a run
started. Model execution reserves the selected installation; independent research can continue.''',
}
