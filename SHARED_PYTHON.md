# Shared Python for official tools

Companion 0.3.0 uses one private Python 3.14 interpreter for the engine and new
official tool packages. It does not modify system Python. NumPy is bundled once
because the included comparison engine needs it. Optional libraries are fetched
only when a tool requires them. Autotune still carries Electron for its existing
interface; this change removes its separate Python and Python libraries.

## Dependencies and uninstall

`shared-python-lock.json` is the reviewed, shipped version set. It records exact
Windows wheel URLs and SHA256 hashes, and the full dependency closure (including
indirect dependencies) for each tool. Packages select `official-python-v1`; they
cannot supply pip options, arbitrary dependency URLs, or replacement versions.
Unknown profiles are rejected with an instruction to update Companion.

The optional library store is `<data>/companion/python-libraries/`. Each locked
distribution has one directory. Tools share those directories, while keeping
their own code and user data separate. `python-bootstrap/sitecustomize.py` enables
only the tool's declared libraries, including wheel `.pth` files. The interpreter
and bundled NumPy remain in the application folder. No duplicate virtual
environments or retained wheel-download cache are created.

Installation verifies/downloads missing wheels into temporary directories before
making them available. It never upgrades an existing dependency in place. A
failed install leaves the previous tool version usable. After successful changes,
cleanup recomputes the union of requirements from installed manifests and deletes
only unreferenced library directories. It skips cleanup if any installed manifest
is unreadable. Locked unused directories may remain until the next change.
User work and settings are never part of dependency cleanup.

The tool being changed must stop first. Other tools can keep running because their
referenced libraries are neither replaced nor removed. Companion's storage lease
prevents multiple app instances from changing the same data folder concurrently.

Installing from a file can require internet for missing dependencies. Once
installed, Python and its libraries work offline. Fully offline first-install
dependency bundles are not implemented. Existing self-contained `.exe` packages
continue to work; replace them with the new shared-format versions to remove their
old Python copies. Third-party tools continue to use the self-contained format.

## Build and test

`build.ps1` packages the standard Python runtime and engine sources instead of a
second PyInstaller runtime. Use the existing Python 3.14 build environment. For
source development, prepare the private runtime once in a fresh destination:

```powershell
.\.packaging-venv314\Scripts\python.exe packaging/build_shared_runtime.py --destination build/shared-dev
```

The sibling tool builders now default to shared packaging and use Companion's
`packaging/build_shared_tool.py`. Where supported, `--standalone` explicitly selects a legacy
builder. Scenario Builder supports shared packaging only. Set `IFS_COMPANION_PATH` if the repositories are not siblings. Examples:

```powershell
.\.packaging-venv314\Scripts\python.exe packaging/build_shared_tool.py --tool ifs-autotune --version 0.2.0
.\.packaging-venv314\Scripts\python.exe packaging/build_shared_tool.py --tool ifs-code-reader --version 0.4.0
.\.packaging-venv314\Scripts\python.exe packaging/build_shared_tool.py --tool ifs-model-vetting --version 0.3.0
.\.packaging-venv314\Scripts\python.exe packaging/build_shared_tool.py --tool ifs-scenario-builder --version NEW_VERSION
```

Builders emit `.ifstool`, `.sha256` and `.release.json`. Publish new versioned
assets before updating the online catalog. Published legacy packages are not
rewritten. Size metadata covers the tool package; additional shared libraries are
excluded because the actual download depends on what is already installed.

Treat `official-python-v1` as immutable. Changing dependency versions requires a
new reviewed profile and migration work, not editing an installed user's library
directories. The current implementation intentionally supports one pinned profile.

Scenario Builder source is in the sibling [ifs-scenario-builder repository](https://github.com/quciet/ifs-scenario-builder). Its `scripts/build_tool.py` passes its source path explicitly; all shared builders also accept `--source PATH` and `--output-dir PATH`. Scenario tests live in that repository.
