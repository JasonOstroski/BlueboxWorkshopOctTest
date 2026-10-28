# Closing summary (fixed shape)

End the run with these three blocks, built from what the run saw.
One line first: "Time to first telemetry:
M min (expected L–H)", M from your first file change to the verification answer; with no
service `reporting`, "not measured" in place of "M min", the reason under Limitations, never an estimate. L–H is
the plan's Expected line, printed under the plan table as "Expected: about L–H min for N
services; first telemetry shows at the end, verification is batched": 11.5 min for the run plus per service .NET 0.9, Java 1.2, Go
2.7, Node 2.8, other 1.5 min, 0.7 of the per-service part at
level 1 or 2, L and H at 0.8 and 1.2 of the sum.

1. **One table, one row per service in the inventory**, in scope or not, exactly once,
   never grouped (out-of-scope ones too; a pointer to the run record replaces no row):

   | service | state | detail |
   |---|---|---|
   | pricing-service | reporting | traces, metrics, logs |
   | calculationservice | skipped | unbuildable_on_host — x86-only image, this host is arm64 |
   | problem-operator | skipped | out_of_scope — runs only under Kubernetes; the compose stack never deploys it |
   | cart | blocked | build_failed — `dotnet restore` NU1101 for OpenTelemetry.AutoInstrumentation; clears once the feed is in nuget.config |

   `reporting` means signals verified in-product, and the detail names which ones.
   `skipped` carries its census reason. `blocked` carries the
   concrete blocker. Each service is in exactly one of those three;
   "configured", "done" or "partial" are not states. A service whose wiring you could not prove is `blocked`.

   The detail of every `skipped` or `blocked` row opens with exactly one reason token, then
   `—` and the concrete detail.
   Reason set:
   - `build_failed` — compile, test or image build failed after wiring, or the exporter guard of Hard rule 9 hit; detail names the error
   - `unbuildable_on_host` — known from the base image before building (arch, platform)
   - `no_runtime` — the runtime probe found no usable container runtime (no
     docker/podman/nerdctl, or its daemon down); nothing was built or started
   - `registry_unreachable` — the reachability probe, or Hard rule 9's version lookup, could not
     connect to the registry or package index the build needs (`http=000`, a connect or DNS
     failure)
   - `endpoint_unreachable` — the reachability probe could not connect to the OTLP endpoint
     (`http=000`, no header sent); wired and build-verified, never started
   - `port_busy` — the service could not bind its port and no free one was taken
   - `no_endpoint` — no OTLP endpoint was available (none in the environment, `otlp-endpoint` exit 2)
   - `no_token` — no ingest header where the services read it (env location, Secret, collector or function configuration), or an env file the run refused to test; nothing started or verified
   - `egress_blocked` — the app ran but exports could not leave the network
     (connection refused or timed out on the endpoint step 2 printed)
   - `auth_rejected` — 401/403 from the exporter or token check: the `Authorization` value or its scheme
     (Hard rule 8), still rejected after one fix
   - `wire_rejected` — the exporter logged 415: JSON on the wire where ingest takes
     `http/protobuf` only (Hard rule 7), still rejected after one fix
   - `endpoint_rejected` — the exporter logged 404, or its host name never resolved: the
     endpoint value (host or path) differs from what step 2 printed
   - `signal_unwired` — no export path for a selected signal (nothing
     registers a reader, bridge or provider for it) and the run did not close the gap
   - `verify_absent` — the app ran and exported, the verification found nothing in the window
     (or only entity-derived `dt.*` keys)
   - `verify_unreadable` — the verification answered, but not in a form you could judge
   - `pii_withheld` — held below the chosen level because its records carry personal data
   - `already_instrumented` — exports OpenTelemetry already; nothing to add, only to route
   - `oneagent_sdk_inactive` — carries a OneAgent SDK that emits nothing without a OneAgent
   - `version_pinned` — held to an older instrumentation line by the repo's runtime version
   - `out_of_scope` — census reason (browser app, off-the-shelf image, never deployed)
   - `not_started` — wired and build-verified, never started in the run (the developer starts it or declined); detail names the start command
   - `user_declined` — the developer kept it out at the question
   - `other: <free text>` — anything else; more than one in ten rows means a missing token
   A `pii_withheld` or `version_pinned` hold on a `reporting` service goes in Limitations,
   opening the line with the same token.

   With the record's `verified_scope` `local`, the table is followed by
   `Verified locally only: no deployed environment has sent data yet.`, and Next steps adds
   `bluebox ask --env '<name you set>' "which services have spans arriving?"` for once it is deployed.
   In any scope, a `target | endpoint and token | environment name` table follows, a row per recorded deploy target: a chart
   or manifest reads a Secret through `secretKeyRef` ([kubernetes.md](kubernetes.md) § Secret)
   and an endpoint env var, a serverless template a secret-backed function environment variable ([lambda.md](lambda.md)); each
   sets its own `deployment.environment.name` in its `OTEL_RESOURCE_ATTRIBUTES`, never the local run's.
   No token value (Hard rule 1). With no recorded target the table is left out.

2. **Limitations.** Only what this run's facts support: no request metrics without inbound
   HTTP, infrastructure not covered without a collector, no logs at level 2 and why.

3. **Next steps.** What the developer does now: where to look in Bluebox, what to run to
   re-verify, and for each `blocked` service the command that clears it; when a probe asked
   for permission this run, the two allow rules,
   `Bash(/bin/sh <skill dir>/scripts/probe.sh runtime:*)` and `Bash(/bin/sh <skill dir>/scripts/probe.sh telemetry:*)`
   with `<skill dir>` written out (never one for `reach`, which takes a host), for the developer to add
   to user-level settings or a git-ignored `.claude/settings.local.json` (never a committed settings
   file, and never written by you); when `<skill dir>` is inside the repository, add that a branch
   can change the script, which then runs unprompted before consent:

   > **Limitations**: `db` and `rabbitmq` are infrastructure and need a collector, which this
   > run did not add.
   >
   > **Next steps**: open the environment view for `docker-compose`. To verify
   > problem-operator, deploy the chart to a cluster and re-run
   > `bluebox ask --env docker-compose "which services have spans arriving?"`.

Also state, once: the files you changed, each package pin as installed, the env vars the
user must supply (the header at the one location the plan's rule-8 row named, never a
second: no shell `export` when that row names a file), the stdout line
`python3 <skill dir>/scripts/build-leftovers.py report --since .bluebox/build-snapshot.json --json`
prints as `line`, if any, verbatim (keep its ids), and anything
that reached your own output that should not have. Name it ("the
ingest token was printed by `<compose> config`; rotate it on the Bluebox Setup page,
`<bluebox-host>/setup`"), never the value or a fragment.

## Handover

Once the three blocks have printed, record them as `--step handover`
([state-resume.md](state-resume.md)); the record's Handover section is that text. Then ask
the run's last question, one question-tool call where there is one
(`AskUserQuestion` in Claude Code): "Done (Recommended)" or "Open a PR". Never ask it as
a plain-text line: a scripted or headless run cannot tell it from the run's end, and
answers it. With no question tool, a headless run
(the request says it is unattended, hub step 3), or a dismissed question, the answer is Done. Record it as
`--decision handover '<question>' '<answer>' developer` (`default` headless).

When `line` counts leftovers, the call adds a question (`line`): "Keep (Recommended)" or "Remove". On "Remove" only, run
`python3 <skill dir>/scripts/build-leftovers.py remove --since .bluebox/build-snapshot.json --ids <the report's ids, comma-separated>`
and print its line verbatim; otherwise remove nothing.
Record it as a second `--decision handover` in the same call.

- **Done**: the changes stay uncommitted and the record stays in `.bluebox/`. No issue,
  branch, commit or PR is created, whatever the repository's own rules ask of a change.
- **Open a PR**: create the branch now (the run wired on the one checked out), copy the
  record to `docs/otel-instrumentation.md` (state-resume.md), commit it with the code, and open the PR with its Handover section as the body. The
  repository's own rules about issues and PRs (an issue first, a PR template, a review
  gate) apply from this answer on, never before it.

Close with one line naming the readable record, `.bluebox/instrumentation-run.md`
(git-ignored, so `git status` does not list it), and `docs/otel-instrumentation.md` when
the developer chose "open a PR"; a run that kept no records says so.

For deeper query patterns load the `bluebox-production-query` skill.
