# IFsCompanion 0.3.8

- Adds persistent, per-chat AI usage for Companion and Scenario Builder, including calls, reported input/output tokens, cached input, failed calls and AI request time. Missing provider usage is shown as a separate approximate character-based estimate; earlier activity is labelled untracked. Confirming or reopening a proposal does not count its usage again.
- Updates usage during active research and keeps receipts when generation fails. Cached and reasoning tokens are subsets, not additional charged token totals. Currency costs are not guessed.
- Integrates Scenario Builder 0.4.4's local parameter checks, compact research and repair feedback. Removes duplicated builder replies from inline reviews and keeps clarification messages in the main conversation.
- Preserves the existing removal of arbitrary research-round cutoffs, saved-progress continuation, optional tool installation, and verified post-update cleanup. Model Vetting remains the only bundled tool.

Update Companion first, then optional **Scenario Builder 0.4.4** in Manage tools. Scenario confirmation and model-run approval remain explicit.

# IFsCompanion 0.3.7

- Removes the main chat's fixed research-round cutoff. Productive research continues until an answer, a validated scenario response, or Stop.
- Detects repeated lookups and repeated results without new information. Reuses cached lookups and offers Continue researching or Revise request with the original request, tool results and links saved.
- Saves completed tool exchanges to local storage; interrupted research can resume after restarting Companion. Connection errors and Stop retain completed work. Continuing never approves a scenario or executes a model run.
- Returns validated Scenario Builder replies directly, avoiding a second AI interpretation and unnecessary tool loops. Update optional Scenario Builder to 0.4.3 to remove its separate metadata-round cutoff too.
- Includes the post-update cleanup improvements: a verified application manifest, cleanup after successful desktop startup, and conservative removal of obsolete owned files and managed update downloads. Unknown files, modified files, settings and selected storage are preserved; locked files are retried. Generated Python bytecode caches are excluded from ownership verification because startup can regenerate them. Source checkouts skip cleanup.

Model Vetting remains the only bundled tool. Existing chats, tool data and saved scenarios are preserved. Provider limits and actual context-size constraints still apply and pause research with progress retained.

# IFsCompanion 0.3.5

- Scenario Builder proposals, confirmation and draft controls appear inline in the main conversation instead of opening a separate scenario interface.
- Scenario revisions use the main composer. Attach or drop a .sce file, add a message and send them together; attaching a file no longer jumps directly to model-run approval.
- Confirmed draft state is saved with the conversation and restored when the task is reopened. Only the latest scenario review is interactive.
- Scenario Builder opens from older tool links return to the main chat. Model execution still requires a separate explicit approval.

Install optional Scenario Builder **0.4.2** through Manage tools to use the integrated review. Model Vetting remains the only included tool. Existing settings, saved scenarios and tool data are preserved.

# 0.3.4

- Validate the compact message composer in the desktop startup check without imposing the previous UI height.

# 0.3.3

- Keep scenario run artifacts with their task, using the scenario name for saved results.
- Add Save to IFs for independent scenario and result copies, with existing-file protection.
- Show model year, logs, errors, saving and working-file recovery status.
- Include the current task workspace and UI improvements.

# 0.3.2

- Show running work with a spinner beside its task in Recents; remove the separate Jobs interface.
- Show saved comparison reports alongside chats in one flat task history.
- Keep narrower user messages on the right and full-width companion responses on the left.
- Keep tool workspaces on the right at narrow window sizes, with a distinct background and divider.
- Add task deletion for saved history and task-owned artifacts.

# IFsCompanion 0.3.0

Official tools now share one private Python runtime and a locked set of libraries.
Missing libraries download automatically when installing a tool. Libraries required
by remaining tools are retained on uninstall, and saved work is preserved. Legacy
self-contained packages remain supported; update them to the new package versions
to remove their separate runtimes. First-time file installs may require internet.

# IFsCompanion 0.2.2

Adds Settings > Companion updates to check stable app releases directly from the
official GitHub repository, download the installer or portable ZIP, and verify
SHA256 checksums. Optional-tool releases are excluded from app update checks.

Installed copies can launch the verified installer and close Companion once
running work has finished. Portable copies receive a verified ZIP and manual
replacement instructions. Existing settings, optional tools and saved work stay
in the data folder. Updates are initiated by the user.

Model Vetting remains the only included tool. Scenario Builder, Code Interpreter
and Autotune are installed and updated separately through Manage tools.

Older app versions need a manual update once to gain these controls.
