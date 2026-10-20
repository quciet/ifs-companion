# Publishing official tools

This directory belongs to the IFsCompanion repository; it is not a separate repo.
Companion reads `catalog.json` over public HTTPS. The catalog is the approval list.
Keep repository write access limited to approved maintainers.

1. Build and test the tool in its development repository.
2. Create a draft GitHub release here, using a tool-specific tag such as
   `comparison-v0.1.0`, and upload the `.ifstool` file and its checksum.
3. Verify package integrity, then publish the release. Mark tool-only releases as
   **not latest** so the latest application release remains easy to find.
4. Update `catalog.json` with the exact versioned asset URL, SHA256, byte size,
   package API/platform, and minimum Companion version. Commit and push it.
5. Verify an anonymous download through Companion's Official tools screen.

Do not put binary packages in Git. Never replace a published version with
different bytes; publish a new version instead. The catalog must identify the
version inside `tool.json`. Companion verifies size, checksum, ID, version, and
compatibility before changing installed files. Failed verification leaves the
current tool untouched. A failed file swap restores the previous version.

Only packages downloaded and verified through this catalog receive recorded
official provenance. A local package does not become official merely by choosing
the same tool ID. Keep Install from file available for offline and third-party use.

Model Vetting stays bundled. Installing its package uses the separate engine for
comparison requests while retaining the shared report/settings folder. Close the
separate engine in Manage tools before updating or removing it. Removing the
package restores the included engine; reports remain available. The comparison
engine package is built with `ifs-model-vetting/packaging/build-tool.py` after
publishing that project's decoder.

## Release metadata

Use each builder's `--release-notes notes.txt` and optional `--release-date`
arguments. Its `.release.json` output supplies `size`, `installed_size`,
`released_at`, `release_notes`, `min_companion_version`, and `sha256`. Copy these
fields into the tool's catalog entry alongside the versioned download URL, and
include them in the GitHub release description. Keep notes as plain text.
For an existing published release, derive sizes from those exact published bytes
and the date from its GitHub publication timestamp. Do not rebuild or replace
published assets just to add metadata. Older packages can receive matching-version
release details from the online catalog.
