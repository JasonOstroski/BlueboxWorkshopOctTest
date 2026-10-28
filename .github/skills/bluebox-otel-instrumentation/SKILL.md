---
name: bluebox-otel-instrumentation
description: >
  Use when asked to add OpenTelemetry to, instrument, or set up tracing or telemetry for a
  service or repository, and the request names Bluebox or names no backend at all. Where
  this skill is installed Bluebox is the backend, so an unqualified "add OpenTelemetry" or
  "instrument this service/repo" request is this skill: load it first, before reading code.
  Do NOT use when the request names a non-Bluebox backend (e.g.
  exporting to Jaeger, Datadog, or a self-hosted collector), for local timing or debug
  logging, or for conceptual questions: that is generic work, not this skill.
  Triggers: "add OpenTelemetry", "instrument this service", "instrument this repo", "set up
  tracing", "OTel setup", "wire up telemetry for Bluebox".
compatibility: Coding agents (Claude Code, Cursor, Windsurf, Copilot, Kiro, OpenCode, Codex)
metadata:
  version: "3.11.2"
  audience: coding-agent
---

# Bluebox OTel Instrumentation

This file is the hub: the order, the Hard rules and the Workflow, complete on its own. A
reference carries a rule's full text or an on-request recipe, never a rule this file
lacks, so a missing reference or script blocks
nothing. Read a reference when the table says so, not from memory. `<skill dir>`
is `${CLAUDE_SKILL_DIR}`, this file's directory.

## Read this reference when

| reference | read it when |
|---|---|
| [export-contract.md](references/export-contract.md) | before the plan table and at steps 2 and 4 |
| [probes.md](references/probes.md) | inventory (runtime and telemetry probes, build-stage read); after approval (reachability line) |
| [language-traps.md](references/language-traps.md) | the plan table and wiring |
| [rules-table.md](references/rules-table.md) | the plan |
| [session-discipline.md](references/session-discipline.md) | before you start or stop anything on the host or search outside the repository |
| [state-resume.md](references/state-resume.md) | before the first file change, after every service, when resuming |
| [verify.md](references/verify.md) | after wiring, before starting anything |
| [closing-summary.md](references/closing-summary.md) | the plan's Expected line; writing the final message |
| [kubernetes.md](references/kubernetes.md) | only on request: Bluebox monitoring a Kubernetes cluster |
| [host-prometheus.md](references/host-prometheus.md) | only on request: host metrics, a Prometheus endpoint, log files, datastore receivers |
| [lambda.md](references/lambda.md) | only on request: an AWS Lambda function |

## Inventory, plan, one question, then work

Levels: `level 1 (traces)`, `level 2 (traces + metrics)`, `level 3 (traces + metrics +
logs, existing logger bridged)`. Write a level out that way the first time you name it in
a turn, in the plan table, the question and the "Taking level N" line.

Your first response is the plan the developer approves:

1. **Inventory.** Every service in `src/` (or the equivalent), jobs and helper binaries
   included (a Dockerfile stage's binary is one): language, and **telemetry today**: `none`;
   `sdk` (OTel packages, initialized by its entrypoint); `custom-otlp` (its own
   OTLP client, no OTel package: already exporting); `agent`; each with its exporter target
   ([probes.md](references/probes.md) § Inventory); in a module with several entrypoints, one it
   shows no initialization for is `none (OTel in manifest, not initialized)`, in scope, its
   recipe the module's existing bootstrap unless wiring finds the entrypoint already
   reaches it. A OneAgent SDK is `none (OneAgent SDK present)`, in scope. Out of scope,
   one line of reason each: browser apps, images this repo builds no code for, services
   the stack never deploys.
   With the first inventory read, start the bounded runtime probe of [probes.md](references/probes.md),
   run as written, as its own tool call in the same message.
   **Telemetry probe, with the reads:** a fixed, read-only grep over the source files of the
   units the inventory lists, returning only file:line;
   no whole-file reads, no execution. With the reads, run the deploy census of [probes.md](references/probes.md).
2. **Plan, per in-scope service** - one table row, a table even for one service: language,
   recipe (zero-code agent, or SDK when nothing zero-code covers it, written as
   `<package>`, its version resolved at install under Hard rule 9), and the files that
   will change, named by convention, not by reading source
   ([rules-table.md](references/rules-table.md) § Plan rows). One `deployment.environment.name` for the run:
   the one the stack already gives its services, else the stack's name; it goes
   into every service's `OTEL_RESOURCE_ATTRIBUTES` (Hard rule 5) and every `bluebox ask --env`:
   the record carries it (`--environment`) and `verify.sh ask` refuses another. In a stack that already exports to an in-stack collector, new rows route
   there too (Hard rule 3), not through a new env file. Under the table: a per-runtime legend of what each level yields,
   the Expected line of [closing-summary.md](references/closing-summary.md), the Runtime line
   ([probes.md](references/probes.md)). Then the Probe line: each host the reachability line
   will contact after approval, with where it came from.
   Shared files get their own line: compose/Helm and run instructions are edited;
   `.gitignore` gains `.bluebox/`;
   `.bluebox/instrumentation-run.json` and its readable record
   `.bluebox/instrumentation-run.md` track the run; `docs/otel-instrumentation.md`
   is written only when the developer chooses "open a PR" at the end.
   The table plus the shared-files line is the allowlist the developer approves. A file the
   plan did not name gets its own question before you touch it; unattended, leave it and
   mark the service `blocked` (`other: edited since the plan` when it changed under you).
   **Rules for this stack** closes the plan ([rules-table.md](references/rules-table.md)):
   a second table, one row per Hard rule that binds the chosen recipe (no rule-2 row for an
   endpoint in the deployment entry), each row carrying
   the value you resolved: `rule | binds here | resolved value`. A row you
   cannot fill means the plan is not ready to ask.
3. **One question.** Ask scope and depth together: the level (recommend 3 with a
   developer present; level 1 is the fast path) and the scope (default: all in-scope
   server-side services). The run is asked here too:
   "Approve and run" approves the plan and the verification start;
   "Approve, I start the app myself" approves the wiring only, and you ask again before
   starting anything. The Runtime line narrows the options (no usable runtime, a daemon
   to start) as [probes.md](references/probes.md) states. With
   a question tool (`AskUserQuestion` in Claude Code) ask through it; keep the question
   text sparse: one status line, one compact line per item, the question.
   The rules table follows the plan
   table in both paths: before the question when one is asked, before the "Taking level
   N" line when not. Without such a tool, ask in plain text and **stop and wait**.
   That pause is the consent gate. A dismissed or canceled question is not an answer:
   stop and say what you would have done. Skip the question only when the request says not
   to ask or says the run is headless (it is unattended); a request that names the level
   (recommend it) or asks to instrument, wire, run or verify still gets it. A tool that refuses or cannot deliver is no sign and neither is how the
   session looks: ask in plain text and stop. Skipped, the level
   is the one the request names, logs asked for means 3, otherwise **level 2**, and you print the
   plan table, the rules table, then one line "Taking level N (<what it yields>): <why>" and
   continue.

**Order is fixed: inventory text, plan table, rules table, the question, then the first file
change.**
A file changed before the table, or before the question was answered or skipped as
above, is a violation. Do not read service source before the
question either, beyond the telemetry probe and the build-stage read.

## Hard rules

Each rule is stated here once; the reference it names carries the full text and binds
exactly as this line does.

1. **Never handle the ingest token, and never make a tool print it back**: not fetched,
   printed or written anywhere, and validating configuration counts as printing; an env
   file shows its names only, through `scripts/env-keys.sh`
   ([export-contract.md](references/export-contract.md) § The ingest token). The token file
   is read by the repo's start command or the runtime, never by a command you type.
2. **Config is external.** All transport via standard `OTEL_*` env vars; nothing hardcoded
   in source, no endpoint in a Dockerfile (the deployment entry is config), no secret committed, env files holding
   real values git-ignored
   ([export-contract.md](references/export-contract.md) § Config is external).
3. **Zero-code first, and never twice.** Auto-instrumentation before code; a service that
   already exports gets no second SDK or log bridge; an in-stack collector is one plan row
   ([language-traps.md](references/language-traps.md) § Zero-code first).
4. **Logs are additive.** Bridge the logger the service already uses with sink, format,
   timestamps, timezone and levels byte-identical, or the service stays at level 2 and you
   say so ([language-traps.md](references/language-traps.md) § Logs are additive).
5. **Identity attributes.** `vcs.repository.url.full` + `vcs.ref.head.revision` from
   build-time values, `deployment.environment.name` from the plan table, cloud attributes
   where a detector exists ([export-contract.md](references/export-contract.md) § Identity
   attributes).
6. **Self-disabling.** With no `OTEL_EXPORTER_OTLP_ENDPOINT` set, every service behaves
   exactly as before instrumentation ([export-contract.md](references/export-contract.md)).
7. **Protocol is `http/protobuf` and metrics use delta temporality.** In Node the
   `*-otlp-http` packages send JSON and ingest answers 415: `*-otlp-proto` or no exporter
   ([export-contract.md](references/export-contract.md) § Protocol and temporality).
8. **The `Authorization` value comes from the Bluebox Setup page whole, scheme included**:
   `Bearer` for a platform token, `Api-Token` for a classic one, never composed from a
   bare token. Its quotes are consumer-specific
   ([export-contract.md](references/export-contract.md) § The `Authorization` value).
9. **Build-verify every touched service** (compile/test with its normal command, never a run) before
   claiming it is wired; fix what you broke.
   Never raise the declared language or runtime version (`go` directive, `engines`, target
   framework, base image tag) to fit an instrumentation release: build in the
   matching image and pin the newest line that supports the version the repo declares, resolved
   at install, after consent and before installing anything, from each candidate's own
   requirement (Go `GoVersion`, npm `engines.node`, PyPI `requires-python`;
   lookups in [language-traps.md](references/language-traps.md)), never `@latest`; never pin a version from memory.
   The plan says "resolved at install"; the closing summary names each resolved number;
   `git diff` shows the declared version unchanged (`go 1.24` → `1.24.0` is the same).
   Then the exporter guard of
   [language-traps.md](references/language-traps.md) runs before the service is recorded.
10. **Narrate progress.** One line at each step boundary: inventory done, per-service
    wired, builds green, app started, verification started and its result. Call the backend
    Bluebox in every line you write; product names such as OneAgent are fine.
11. **Finish in one session.** Never end your turn while builds, traffic or verification
    are pending: wait in the foreground with a bounded loop, never through a background
    tool call, and stop only for the asks this skill mandates
    ([session-discipline.md](references/session-discipline.md)).
12. **The host is not yours.** Change only the repository; on the host, build and start
    the repository's own services and stop what you started, by its own PID, nothing
    else: never kill by port or name, whatever the repository's notes say; a bound port
    means another port or a report; no `sudo` on the host, no elevated change in the runtime's VM
    ([session-discipline.md](references/session-discipline.md)).

## Workflow

1. Inventory, plan, the rules table, and the one question (above). No request reaches the
   Probe line's hosts before the plan is approved; then run the reachability line of
   [probes.md](references/probes.md) beside step 2's first reads. Unreachable, no retry: a
   registry leaves the run wiring only (`registry_unreachable`), the OTLP endpoint stops it
   after build-verify (`endpoint_unreachable`).
2. **Environment, then CLI** ([export-contract.md](references/export-contract.md) §
   Endpoint and CLI ladder holds the detail). Look at the environment
   first, never with `env` or `printenv` (Hard rule 1), the header for presence and scheme
   only; an exported endpoint IS the endpoint. Else the run's first CLI call, from the repository root:
   `BLUEBOX_JOURNEY_TYPE=instrumentation bluebox otlp-endpoint`; exit 1 or 2: keep wiring,
   never poll, and after exit 2 verification is `blocked` unless the environment carries an
   endpoint; a CLI below v0.84.0 is the user's to update, its exit 2 provisional. Never create
   `.env.otel.bluebox-template`; one an older CLI left is no input: leave it as it is, never read
   the endpoint from it, never wire it as an env file.
3. Wire the selected services **one at a time**: wire, build-verify (Hard rule 9), record
   ([state-resume.md](references/state-resume.md)), then the next. Update the start
   command and deployment config (compose/Helm/process manager) with non-secret defaults
   only, the token only as a runtime env reference, and the run instructions the repo
   already has. Wire on the branch already checked out: only "Open a PR" makes a branch.
   Right before the run's first image build, once per run (kept on resume), with the probe's
   runtime (docker or podman, never nerdctl) and the record guard of
   [state-resume.md](references/state-resume.md) passed:
   `python3 <skill dir>/scripts/build-leftovers.py snapshot --runtime <rt> .bluebox/build-snapshot.json`.
4. **The ingest header is a precondition of the run**
   ([export-contract.md](references/export-contract.md) § Header precondition). Only for
   a run the question granted or the user approves later; one the user starts or declines
   stays `not_started`, and a service step 1 blocked never gets here. Before the start,
   the traffic, the settle or `bluebox ask`, test the env location step 3 named for
   presence, never printing the value, as that section says. Present: its token check.
   `accepted` goes on to step 5. `unchecked` asks the user first: "Continue anyway" is
   step 5, "Skip" is skip; headless, step 5.
   `rejected` stops; twice is skip (`auth_rejected — token check <code>`). The fix:
   Rotate on **Settings → Setup** and re-copy; on a manual connection (no Rotate),
   re-paste into **Workspace OTLP ingest token**; else a classic `dt0c01…` token with
   `openTelemetryTrace.ingest`, `metrics.ingest` and `logs.ingest`, as `Api-Token`, not
   `Bearer`. Absent, user
   present: **stop** and send that section's one message, never asking to see the value
   or offering a command that captures it;
   re-test on done, and absent twice counts as skip. On skip, or headless with the header absent or `rejected`: no start against Bluebox, no traffic, no receiver of any kind, no
   `bluebox ask`: the selected services are
   `blocked` (`no_token — …`; rejected: `auth_rejected — token check <code>`; an `unchecked` Skip: `not_started — token check unchecked`; with no endpoint at all `no_endpoint — …`) with the
   runnable start command, header only by reference, in Next steps. Never start with an
   empty `OTEL_EXPORTER_OTLP_HEADERS` against the Bluebox endpoint.
5. With the run granted (at the question, or by the offer in [verify.md](references/verify.md))
   and the header present (step 4): start the app once with its
   normal dev command (noting its PID: Hard rule 12), or the probe's `<compose> up --build`
   (step 3's snapshot first if not yet taken; never a literal `docker` it did not list), adding for this verification start
   only the SDK export knobs,
   `OTEL_METRIC_EXPORT_INTERVAL=10000 OTEL_BSP_SCHEDULE_DELAY=1000 OTEL_BLRP_SCHEDULE_DELAY=1000`
   (the committed run command keeps the SDK defaults), and the runtime's
   diagnostics switch from [language-traps.md](references/language-traps.md). A bound
   default port: start on the next `PORT` that verify.md's `lsof` check prints nothing for,
   checked before the start command, not in it, and say so; never investigate what holds it.
   Drive one request per instrumented service, one it serves normally, never one built to fail (the repo's load generator or reverse-proxy routes when present) and record the window start.

## State and resume

An interrupted run must not start over. Once the question is answered, before any service
file changes, write `.bluebox/instrumentation-run.json` (git-ignored) with the revision,
the level, the scope and one entry per planned service; update one entry the moment its
build-verify passes or it is marked `blocked` or `skipped`, replacing the file rather
than writing over it. `python3 <skill dir>/scripts/state-update.py` is that call, and the
same script takes each step's report, as printed, the moment the step ends: `--step scan`
and `--step plan --environment '<env>' --decision plan '<question>' '<answer>' developer` right after the answer,
the scan with a `--deploy-target` per census target line (each value in single quotes, a `'` inside one written `'\''`), `--step instrument` once
the last service entry is recorded, `--step verify` once the batched ask is judged,
`--step handover` with the closing summary. A report never passed leaves its section
`_pending_` (`_not run_` once the handover is recorded); Instrument always prints its
services table. No secrets in it, ever. Its shape, resume and readable record:
[state-resume.md](references/state-resume.md).

## Run it, then verify

If the question did not grant the run, offer it after wiring and build-verify and ask before starting anything; declined, or no
user and no start, those services are `blocked` with a reason-set token. Verification happens EXACTLY once, after all wiring and the traffic window,
only with the ingest header present (step 4), as [verify.md](references/verify.md) says
and `bash <skill dir>/scripts/verify.sh` runs: read the exporter's own log for its failure
lines before you wait (`verify.sh logs …`), fix, restart, read again; settle;
then ONE batched ask, `verify.sh ask …` scoped to the recorded environment
name (`bluebox ask` by hand only where the script is missing). Every count you quote names that scope, and a scoped count is never
compared with an unscoped one. Never report `reporting` for a service you saw no signal
from. Before finishing: the secrets scan, the verification table into the record
(`--step verify`), and the fresh-window offer after a blocked window.

## Closing summary (fixed shape)

End the run with the three blocks of [closing-summary.md](references/closing-summary.md),
built from what the run saw: "Time to first telemetry" first,
then **1.** one table, one row per service in the inventory (`service | state | detail`),
**2.** Limitations, **3.** Next steps. `reporting`, `skipped` and `blocked` are the whole
vocabulary, and a `skipped` or `blocked` detail opens with exactly one token of the
reason set that file defines, then `—` and the specifics; a reason outside the set is
written `other: <free text>`. Never invent a token. Then one question, "Done
(Recommended)" or "Open a PR", never as plain text; headless it is Done, and nothing is
filed before "Open a PR" (that file, § Handover).
