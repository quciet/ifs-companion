# IFsCompanion 0.2.1

Released October 20, 2026.

Model Vetting is the only tool included by default. Scenario Builder is now a
separate optional `.ifstool` download, consistent with Code Interpreter and
Autotune. Install it through Settings > Manage tools; it appears in Tools only
after installation. The Companion distribution excludes its UI and compiler.

This corrects the bundling in 0.2.0. Update Companion to 0.2.1, then install
Scenario Builder 0.1.0 if desired. Existing settings, comparisons, and previously
generated scenarios remain untouched. Files exported with the earlier bundled
builder remain in their original data folder; no automatic move is performed.

Shared AI and storage settings remain in Companion. Optional tools receive the
current settings paths and keep their mutable files in per-tool storage.
Scenario Builder uses the selected IFs installation and shared AI connection.

Download the Windows x64 installer or portable ZIP. Verify against SHA256SUMS.
The installer is unsigned; the portable app requires WebView2. IFs model files
are not included. See the separate Scenario Builder release for its tool package.
