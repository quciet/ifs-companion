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
