# Chat workspace integration

## Implemented source behavior

Companion owns persistent independent chats in `companion/conversations.sqlite3`.
Each chat uses the shared provider configuration and pins the selected installation.
Changing installations requires a new chat. A busy chat does not prevent a different
chat from responding. Stop targets a conversation and, when applicable, its active
Scenario Builder session; provider cancellation takes effect after the current call.

`conversations.py` runs a bounded, allowlisted tool-calling loop.
`agent_workflows.py` holds focused explanation, scenario, comparison and tuning
instructions. This is application guidance, not installation-specific cached data.

`chat-workspace.js` embeds existing local interfaces in per-chat tabs, with an
expand control. Model Vetting accepts a proposed selection through
`companionView.open(context)` or opens an existing report without rerunning it.
Comparison submission records a report link in its originating chat. The assistant
can list reports and read bounded numerical summaries for follow-up explanations.

Scenario Builder retains its compiler, validation, review graphs, confirmation,
preview and export. Main-chat scenario requests reuse its existing AI workflow.
This is a transitional adapter: there are still two provider loops when the main
assistant delegates a scenario request. Scenario sessions and validated drafts are
persisted by the package. Approval remains in the existing review interface.
Revising the scenario invalidates previous confirmation/export tokens.

Code Interpreter provides authenticated shared evidence and read-only research
operations over its prepared index, separate from its legacy single question
worker. Explanation and scenario planning can use the same knowledge service.
The source index must first be prepared through the knowledge interface. A bundled
source version is not automatically verified against the selected installation.

Scenario Builder and Code Interpreter are capabilities rather than Tools sidebar
entries. They remain installable/manageable packages. Model Vetting and Autotune
retain direct standalone interfaces. The existing comparison history is retained;
no additional Saved Work destination was introduced.

## Execution reservation

`execution.py` holds an installation-wide OS file lock and checks for native IFs
processes before granting a reservation. Failure to inspect processes blocks
execution. The lock is also exclusive across Companion processes using different
storage directories. Further Autotune integration is outside this phase; its
previously added reservation bridge is unchanged.

The footer reports Companion's reservation, not a continuous assertion that an
externally launched IFs process is absent. A native IFs application does not honor
Companion's lock, so it can still be launched externally after a reservation.

## Approved scenario execution

After confirming a scenario proposal, choose **Review model run** in its review
tab. Alternatively, use **Run .sce** in the main chat to select an existing UTF-8
file up to 1 MB. File validation and execution do not require an AI connection.
The installed Scenario Builder must expose the `approved_execution` capability.

Companion snapshots the exact bytes, SHA256, installation identity, baseline
fingerprint and requested horizon. A separate review tab displays the file and
horizon; **Approve and run** is the execution action. The assistant can prepare
this review but cannot approve it. Changing the draft or installation requires a
new review. Repeated Start requests for an approval return its existing job.

`scenario_runner.py` follows the established Autotune CLI contract:

```
net8/ifs.exe 5 <end-year> -1 true true 1 false --log <job-log> --websessionid <job-id>
```

Before launch it backs up `Scenario/Working.sce`, `RUNFILES/Working.run.db`,
`SAMWorking.db`, `IFsPopWork.db`, `ifsForDyadicWork.db` and `progress.txt`, including
which files originally existed. It prepares Working from `IFsBase.run.db`, SAM
from `DATA/SAMBase.db`, and dyadic work from `DATA/IFsForDyadic.db` when present.
It installs only the approved scenario and clears stale progress. Existing working
database journals block preparation. The supported horizon is the installation
base year through 2100.

Exit code zero alone is insufficient: fresh progress must report the requested
final year and the captured output must pass SQLite integrity checking. Outputs,
approved scenario bytes and logs live under the active storage root's
`runs/<job-id>/`. Scenario and result filenames use the scenario stem, for example
`DiwWorld.sce` and `DiwWorld.run.db`. Legacy runs retain their original filenames. Working files are restored after success, failure or cancellation;
backups are then removed. Completed outputs and concise logs remain.

If restoration fails, backups and a `.companion-recovery.json` marker remain.
Managed execution is blocked until **Restore working files** succeeds. Recovery
checks the original job, installation, reservation and native-process state.
Interrupted jobs can be recovered after restart. Do not manually remove recovery
markers or backup directories before recovery.

Completed outputs appear in the shared run catalog and link to Model Vetting.
Comparisons of immutable saved runs can proceed during model execution. Reading
mutable working files is blocked while IFs owns the installation; a comparison
already reading those files blocks model preparation.

## Unified jobs

`jobs.py` persists jobs and ordered events in `companion/jobs.sqlite3`: chat
responses, scenario runs, comparisons (including direct tool submissions), and
knowledge preparation/research from the existing interface. Jobs retain their
originating chat when applicable, progress, terminal status and result references.
Existing comparison results are adopted without rerunning them. Autotune jobs are
excluded from this phase.

The chat shows its jobs; the **Jobs** toolbar button lists all tracked work. A job
tab supports progress/results, targeted Stop and recovery. Closing a workspace tab
does not stop a job. Application shutdown stops owned runs and waits for working
file restoration. Installer handoff is blocked while managed work is active.
Completion messages link to the job and comparison setup; the assistant can read
actual statuses and saved output paths using its job operations.

API routes: `/api/runs/prepare`, `/api/runs/approval`, `/api/runs/start`, `/api/jobs`,
`/api/jobs/events`, `/api/jobs/cancel`, `/api/jobs/recover`. Mutating routes require
Companion authentication; scenario previews and validation use the authenticated
local package service.

## Remaining work before the complete proposed workflow

- Replace the transitional scenario provider-loop adapter with shared workflow
  execution if one provider loop is required throughout.
- Add main-chat scenario-editing attachments; existing-file execution is supported,
  while attachment editing remains in the Scenario Builder interface.
- Add contextual profile/result opening in Autotune if requested in a later phase.
- Persist open workspace tab descriptors across application restarts. Conversations,
  report links and scenario sessions persist; open tab DOMs currently last only for
  the browser session.
- Package Companion and updated capability/tool packages as needed. Older packages
  receive capability-update messages. No Autotune release is required for this
  phase. Source changes do not update an installed or `dist/` copy.

## Verification

Use the existing shared development runtime for Python tests; the bare bootstrap
Python does not include NumPy. Tests use temporary data directories and mocked
providers. `tests/chat_browser_fixture.py` uses a small subprocess simulator and
the real comparison engine. It never runs native IFs or calls an external provider.
Browser verification covered approval, execution, output capture, GDP comparison,
saved-report reopening and the Jobs list. Screenshots are under `output/playwright/`.

No native IFs model run, live-provider quality evaluation, installer build or
publication was performed. Verification did not modify the user's IFs installation
or saved model runs.


### Run status and Save to IFs

The run card reports the latest model year, requested end year, elapsed time,
last year update, task-result saving state and working-file restoration state.
Model console and IFs log tails are available during execution and after failure.
Saving and validation finish before the runner reports a saved task result;
restoration is reported separately, including recovery failures.

Completed runs offer **Save to IFs**. This explicitly copies the task's scenario
into the original installation's `Scenario/` folder and its result into `RUNFILES/`,
using the chosen scenario stem for both files. Existing files are never overwritten;
choose a different name on conflict. Working and IFsBase are protected names.
The installation must be idle and recovered. If copying fails, newly created
partial copies are removed and task originals remain available.

Deleting a task removes its owned scenarios, results and logs. Independent copies
saved to IFs remain. Saving uses the same task lifecycle lock as deletion.
