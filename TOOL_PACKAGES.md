# IFs tool packages, format 1

A `.ifstool` file is a ZIP with `tool.json` at the root and all required Windows
x64 program files. Packages run trusted native code. This is an internal package
format, not a sandbox or a way to install arbitrary ZIP files. Only install tools
from your team. Optional tools can be installed, updated from a newer package,
and uninstalled independently of Companion. Same-version repair is allowed;
downgrades are rejected. An installed `ifs-model-vetting` package overrides the
included comparison engine. Uninstalling it restores the included version and
preserves shared settings and reports. Official downloads are listed in
`official-tools/catalog.json` and hosted as versioned GitHub Release assets.

Example manifest:

```json
{"id":"ifs-autotune","name":"IFs Autotune","version":"0.1.0",
 "api_version":1,"platform":"win-x64","kind":"web-service",
 "entrypoint":"electron/IFsAutotune.exe"}
```

The ID is stable across updates. The entry point is a relative `.exe` path.
Do not include personal settings, working inputs, results, credentials, or source
checkouts. Include dependency licenses and any clean starter templates needed.
ZIP paths may not escape their installation folder or contain links.

## Runtime contract

Companion launches the executable with no shell or package-defined arguments:

- `IFS_COMPANION_MODE=1` selects embedded operation.
- `IFS_COMPANION_PID` identifies the owning Companion process; exit when it disappears.
- `IFS_TOOL_DATA_DIR` is a persistent per-tool folder outside program files.
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
failed file swap restores it. Close the tool before updating or removing it.
