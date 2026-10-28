# State and resume

Once the question is answered, before any service file changes, write `.bluebox/instrumentation-run.json` (`.bluebox/` git-ignored): the
repository (its origin URL without userinfo), the revision (`git rev-parse HEAD`), the level, the scope, and one entry per planned service -
`status` (`planned`, `wired`, `blocked`, `skipped`), the files its plan row named as
repository-relative paths with the sha256 of their content after your edit, and the `reason`
and `detail` the closing summary will carry:

```json
{"repository": "<origin URL>", "revision": "<git rev-parse HEAD>", "level": 3, "scope": "all",
 "services": [{"name": "pricing-service", "status": "planned",
               "files": [{"path": "src/pricing-service/main.go", "sha256": "..."}],
               "reason": "", "detail": ""}]}
```

Update one entry the moment that service's build-verify passes or it is marked `blocked`:
`scripts/state-update.py` in this skill's directory is that call, run from the repository root:

```bash
python3 <skill dir>/scripts/state-update.py --name 'pricing-service' --status wired \
    --file 'src/pricing-service/main.go' --file 'src/pricing-service/Dockerfile' \
    --detail 'zero-code Go SDK, logs bridged'
python3 <skill dir>/scripts/state-update.py --name 'cart' --status blocked \
    --reason build_failed --detail 'dotnet restore NU1101 for OpenTelemetry.AutoInstrumentation'
```

Each value goes in single quotes, a `'` inside one written `'\''`.

It takes `--reason` only for a
`blocked` or `skipped` entry, as one token from the reason set (or `other: <free
text>`), and refuses a name, reason or detail that carries a token prefix, an
`Authorization` value or a URL with userinfo.

No secrets in it, ever. Before the first read, write or copy of either record, run from the repository root
`test ! -L .bluebox && test ! -L .bluebox/instrumentation-run.json && test ! -L .bluebox/instrumentation-run.md && test ! -L docs && test ! -L docs/otel-instrumentation.md`:
non-zero means a committed link: say so and run without the records and the PR copy. On start, read the file only if it parses, carries those fields and
every path is relative and inside the repository; anything else is stale: say so and start
fresh. Same revision, same scope and level, a service still `planned`: a resume.
Say "resuming: N of M wired", print the plan table with each service's recorded status (a
`blocked`/`skipped` row as `reason — detail`), take the recorded level as the answer, and
continue from the first service not `wired` or `blocked`. Per named file of that service:
content matching the recorded hash is your finished edit; matching the revision is
untouched, wire it; anything else is the developer's own work. Ask before touching it
(unattended: leave it, mark the service `blocked` with `other: edited since the plan`).
Nothing left `planned` is a finished run; a different scope, level or revision is not a
resume: say what it records and ask whether to start over (unattended: start over
and say why). The developer removes the file when done; the closing summary names it under
next steps when anything is not `wired`.

## The readable record

`state-update.py` renders `.bluebox/instrumentation-run.md` from the JSON
at every call, replaced the same way: a header (repository without userinfo, revision,
started, the environment, the verified scope, the deploy census, a five-entry progress line Scan · Plan · Instrument · Verify · Handover, status), a
decisions table, then one section per step, `_pending_` until reached, Instrument led by the
entries' own table. Never write it yourself. As each step's report prints, pass the same
tables and lines on stdin (the table below), and each answer as a decision (rescopes and retests
included), by `developer`, or `default` headless:

```bash
python3 <skill dir>/scripts/state-update.py --step plan --environment '<env>' --decision plan '<question>' '<answer>' developer <<'BLUEBOX_RECORD_END'
> <the step's report as printed>
BLUEBOX_RECORD_END
```

Every report line opens with `> ` (a blank one `>`), which the script strips, so no line can
close the heredoc early, the fixed end line included; `--decision` repeats per answer. One
call per step, the same shape, the moment the step ends; a report never passed leaves its
section `_pending_` (`_not run_` once the handover is recorded), and until the handover is
recorded the Status line names the first step not passed:

| call | when | the report carries |
|---|---|---|
| `--step scan` | right after the answer | the inventory with telemetry today, the runtime line |
| `--step plan --environment '<env>' --decision plan '<question>' '<answer>' developer` | right after `--step scan` | the plan table, prerequisites, the rules table |
| `--step instrument` | after the last service entry | the files changed, per service |
| `--step verify` | once the batched ask is judged | the verification table, the window, the attempts |
| `--step handover` | with the closing summary | the run and re-verify commands, limitations, next steps |

`--environment` records the plan table's environment name, the one value of
`deployment.environment.name`, as `environment` in the JSON and an Environment line in the
readable record. `verify.sh ask` reads it from there: with no `--env` it asks in that name, and
an `--env` or `env=` that differs is refused. A developer who re-scopes the run to another
name answers a question first; record it as `--environment '<new>' --decision <step> '<question>'
'<answer>' developer` in one call, since a changed name without the developer's decision is refused, and a headless run
(`default`) never re-scopes itself. Never
re-derive the name from the stack's settings at verification.

`--deploy-target '<kind>: <path>'` per census target line goes with `--step scan`; `--verified-scope
local` with `--step verify` when the verified stack ran on this machine, `deployed` only when the plan
named a deployed environment and the run started nothing.

It refuses a report or decision carrying a token prefix, an
`Authorization` value (a placeholder too) or a URL with userinfo: the run command names where
the header lives, never its assignment. Never raw command output or customer data either
(Hard rule 1). On "Open a PR" at the Handover question ([closing-summary.md](closing-summary.md)
§ Handover), copy it to `docs/otel-instrumentation.md` under the same rule,
commit it with the code, and use its handover section as the PR body.
