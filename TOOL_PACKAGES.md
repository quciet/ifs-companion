# IFs tool packages, format 1

A `.ifstool` file is a ZIP with `tool.json` at the root and its Windows
x64 program files. Official shared-Python packages download missing libraries separately. Packages run trusted native code. This is an internal package
format, not a sandbox or a way to install arbitrary ZIP files. Only install tools
from your team. Optional tools can be installed, updated from a newer package,
and uninstalled independently of Companion. Same-version repair is allowed;
automatic downgrades are rejected; explicitly confirmed file installs may use older or prerelease versions. An installed `ifs-model-vetting` package overrides the
included comparison engine. Uninstalling it removes comparison from the sidebar and preserves shared settings and reports. Official downloads are listed in
`official-tools/catalog.json` and hosted as versioned GitHub Release assets.

Example manifest:

```json
{"id":"ifs-autotune","name":"Autotune","version":"0.1.0",
 "api_version":1,"platform":"win-x64","kind":"web-service",
 "entrypoint":"electron/IFsAutotune.exe"}
```

The ID is stable across updates. The legacy entry point is a relative `.exe` path. Official shared-Python packages add `"python_profile":"official-python-v1"`, require Companion 0.3.0+, and may use a `.py` entry point. See [Shared Python](SHARED_PYTHON.md).
Do not include personal settings, working inputs, results, credentials, or source
checkouts. Reviewed, versioned source snapshots for Code Interpreter are permitted; omit Git history, credentials, and build outputs. Include dependency licenses and any clean starter templates needed.
ZIP paths may not escape their installation folder or contain links.

## Runtime contract

Companion launches the executable with no shell or package-defined arguments:

- `IFS_COMPANION_MODE=1` selects embedded operation.
- `IFS_COMPANION_PID` identifies the owning Companion process; exit when it disappears.
- `IFS_TOOL_DATA_DIR` is a persistent per-tool folder under the selected Companion storage root. Never infer storage from the executable or current directory.
- `TEMP`, `TMP`, and `TMPDIR` point to the selected storage root's `temp` folder. Use them for disposable files rather than hard-coded system paths.
- `IFS_AI_SETTINGS_FILE` points to shared AI configuration. Read it for each new request so edits take effect without a restart. Endpoint and model are plain text; `protected_key` is base64 current-user Windows DPAPI ciphertext. Do not return the decrypted key to the browser, log it, or copy it into tool data. An absent file means AI is not configured.
- `IFS_SETTINGS_FILE` points to Companion shared settings.json (Companion 0.2.1+). Read it per operation to use installation changes without restarting the tool.
- `IFS_INSTALLATION` is the shared IFs folder at launch, if configured.
- `IFS_TOOL_TOKEN` is a random per-launch secret. Require it in the
  `X-IFs-Tool-Token` header on **every** local service request.
- `IFS_TOOL_READY_FILE` is a unique file path. Bind an available loopback port,
  then atomically write `{"port":12345}` here when ready.

Serve the tool UI at `/`, use relative assets and API URLs, and expose
`GET /bridge/status` returning `{"running":false}` (true whenever user work is
active). Companion proxies this service into `/tools/<id>/`; it never loads a
remote website. For browser POSTs include `X-Companion-Token` from the parent
document's `meta[name=companion-token]` element. No CORS is necessary.

Expose authenticated `POST /bridge/shutdown` for graceful shutdown and stop child
processes when exiting. Watch the owning process for host crashes. Keep stdin open
if your runtime supports it; its EOF also signals shutdown. Autotune's `desktop/companion-host.js` and `companion-bridge.js` provide
a working example that reuses Electron handlers. Log stdout/stderr to the file
Companion supplies (`tool-data/<id>/tool.log`). Never put mutable state in the
installation directory. Do not automatically migrate or delete user data during
uninstall; tool-specific schema migrations belong to the tool itself.

Companion validates/extracts updates into a temporary directory before replacing
the installed version. Failed validation leaves the old version intact, and a
failed file swap restores it. Companion closes idle tools before updates or removal; active work must be stopped first.

## Embedded session controls

Expose `window.companionSession` from the tool UI with `canGoBack()`, `back()`,
and async `stop()` methods. Back must navigate inside that tool, never between
Companion tools. Post `{type: 'tool-navigation'}` to the same-origin parent when
the tool's navigation state changes. Stop must wait for work to finish stopping,
then show the starting screen while retaining form selections and saved results.
Reject on failure so Companion can display an error; do not reload the iframe or
clear user settings. Companion keeps a separate iframe for each opened tool.
Older packages without this interface must be updated to use the Stop button.

## Release information

Optional tool.json fields: `released_at` (YYYY-MM-DD), `release_notes` (plain text,
up to 8,000 characters), `min_companion_version` (major.minor.patch), and
`installed_size` (approximate unpacked bytes). Companion preserves these fields
for offline/file installs and calculates actual archive and unpacked byte counts
at installation, overriding package-supplied sizes. Older packages remain valid.

Tool builders accept `--release-date YYYY-MM-DD` and `--release-notes notes.txt`.
The default date is the UTC build date. They embed notes, compatibility, and an
unpacked-size estimate in the package, then emit a `.release.json` sidecar with
exact archive size, unpacked size, and SHA256. Download size lives in this sidecar
and the catalog because it cannot reliably be embedded in the archive whose
size it describes. The package's own manifest must remain under 16 KiB.

Manage tools shows a size summary and Release details. It distinguishes the
installed version from a different latest official version. Sizes exclude saved
work, generated indexes, and temporary installation space.
