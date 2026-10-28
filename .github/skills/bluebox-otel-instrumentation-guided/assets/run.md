# Run file `.bluebox/instrumentation-run.md`: the hub's readable record
# (../bluebox-otel-instrumentation/references/state-resume.md § The readable record).
# The hub's scripts/state-update.py renders it whole at every call; you never write it. It
# fills the title, the Repository, Started, Environment (once recorded), Verified, Deployment targets (once recorded), Progress and Status lines, the Decisions table, the
# headings, the Instrument counts and state table, and `_pending_` (`_not run_` once Handover
# is in) under a step with no report. You pass the rest: per step, the report under its
# heading, shaped as below (the moment's block without its stepper line and strip), and each
# answer as a decision. Progress marks a step with a report `✓ `, one left out `– `. Plain
# markdown, no HTML; glyphs ⚠︎ / ℹ / ✓ / ✗ only. Never raw command output, a header value, a
# token, a credential-bearing URL or customer data (Hard rule 1). On "Open a PR": copied to
# docs/otel-instrumentation.md as rendered.

# OpenTelemetry instrumentation run: {{repo_name}}

**Repository** `{{repository_url}}` @ `{{revision}}`

**Started** {{started_at}}

**Environment** `{{env}}` (every `bluebox ask --env` of the run)

**Verified** {{locally only - no deployed environment has sent data yet, or `<env>` (deployed)}}

**Deployment targets** {{`<kind>: <path>` per deploy census line, · between}}

**Progress** {{glyph}}Scan · {{glyph}}Plan · {{glyph}}Instrument · {{glyph}}Verify · {{glyph}}Handover

**Status** {{step, or Finished}} · {{n_wired}} of {{n_in_scope, skipped ones left out}} wired · {{n_blocked}} blocked · {{n_skipped}} skipped

## Decisions

| When | Step | Question | Choice | By |
|---|---|---|---|---|
| {{decided_at}} | {{step}} | {{question}} | {{choice}} | {{by}} |

## 1. Scan

{{n_components}} components · {{n_in_scope}} in scope · {{n_excluded}} excluded

**Runtime** {{runtime_line}}

| Service | Language | Telemetry today | In scope | Why |
|---|---|---|---|---|
| {{service}} | {{language}} | {{telemetry_today}} | {{in_scope}} | {{reason}} |

## 2. Plan

**Scope** {{scope}} · level {{level}} ({{level_written_out}}) · env `{{env}}` · expected {{low}}–{{high}} min

{{the approved plan table}}

Shared files: {{shared_files_line}}

{{the rules table}}

Prerequisites:
- ✓ {{satisfied}}
- ⚠︎ {{developer_must_act}}
- ℹ {{already_handled}}

## 3. Instrument

Wired {{n_wired}} · Blocked {{n_blocked}} · Skipped {{n_skipped}}

| Service | State | Detail |
|---|---|---|
| {{service}} | {{state}} | {{reason}} — {{detail}} |

| File | Change |
|---|---|
| `{{file}}` | {{change}} |

## 4. Verify

`--env {{env}}` · window {{t1}}–{{t2}} · reporting {{n_reporting}} of {{n_started}} · attempts {{n_attempts}}

| Service | Spans | Metrics | Logs | `vcs.repository.url.full` | State |
|---|---|---|---|---|---|
| {{service}} | {{spans}} | {{metrics}} | {{logs}} | {{repository_url_seen}} | {{state}} |

- ⚠︎ {{finding}}

## 5. Handover

{{the closing summary table}}

Run with telemetry:

```bash
{{run_command}}
```

Re-verify:

```bash
{{verify_command}}
```

You supply (names only): `{{env_var}}` — {{note}}

Limitations:
- {{limitation}}

Next steps:
- {{next_step}}
