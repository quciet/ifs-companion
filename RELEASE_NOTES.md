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
