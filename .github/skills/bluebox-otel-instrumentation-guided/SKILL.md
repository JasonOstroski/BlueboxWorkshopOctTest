---
name: bluebox-otel-instrumentation-guided
description: >
  Use ONLY when the user asks by name for the guided, step-by-step flow of instrumenting a
  service or repository with OpenTelemetry for Bluebox: "guided instrumentation", "guided
  OTel setup", "walk me through instrumenting", "step-by-step instrumentation". A plain
  "add OpenTelemetry" or "instrument this service" request belongs to
  bluebox-otel-instrumentation, not to this skill, and so does OpenTelemetry work for a
  non-Bluebox backend.
compatibility: >
  Claude Code (asks through AskUserQuestion); other coding agents ask numbered questions.
  Needs bluebox-otel-instrumentation installed in the same skills directory.
metadata:
  version: "1.4.3"
  base: bluebox-otel-instrumentation
  base_min_version: "3.9.1"
  audience: coding-agent
---

# Bluebox OTel Instrumentation, guided

This skill changes how an instrumentation run looks, not what it does. The run itself is
**bluebox-otel-instrumentation** (the hub), installed next to this skill: its order, Hard
rules, Workflow, state and resume, verification and closing summary bind unchanged. This
file adds the five moments the developer sees, how each decision is asked, and the run
file. It restates no rule; where it names one, the hub's text is the rule.

## Before your first response

1. Run `python3 <this skill's base directory>/scripts/check-base.py`, the one script this
   skill has. It reads the hub's `metadata.version` against this skill's
   `metadata.base_min_version` and prints one line. Anything but an `ok:` line ends the
   run, and nothing in this conversation is instrumented until the developer fixes it:
   reply with that line, which names its fix, and nothing else. Do not offer or run
   bluebox-otel-instrumentation itself instead, "plain", "non-guided" or "at its own
   version": the copy installed here is the older rules this check keeps out. Do not
   install or update a skill; that is the developer's step. Do not rebuild the workflow
   from memory. A go-ahead, "take the recommended option" or "run it anyway" gets the same
   reply.
2. Only after an `ok:` line: the directory it names at the end is the hub, resolved and
   checked, and the only path you read it through. That absolute path is the hub's
   `<skill dir>` for the whole run: every `references/…`, `scripts/…` and `<skill dir>` in
   the hub means that directory, never this one, and so does every
   `../bluebox-otel-instrumentation/…` in this file. So
   `../bluebox-otel-instrumentation/scripts/state-update.py` and
   `../bluebox-otel-instrumentation/scripts/verify.sh` run by that absolute path.
3. Read `../bluebox-otel-instrumentation/SKILL.md` from that directory, whole, with your
   file-read tool, and follow it as the run's contract. Do not invoke it as a second skill.
4. Read [assets/terminal.md](assets/terminal.md) and
   [assets/run.md](assets/run.md) once.

## The five moments

A run shows five moments, in this order: Scan, Plan, Instrument, Verify, Handover. Each is
its block from `assets/terminal.md`, written in full as your own text: the stepper line
where the paragraph below puts it, the strip, then the hub's own tables for that step, in
the hub's shape. The block is the
step report, printed whether or not the moment asks anything; a sentence of narration in
its place fails this variant.

| moment | shows the hub's | when |
|---|---|---|
| Scan | Inventory (its item 1) with the runtime probe | first response |
| Plan | plan table, legend, Expected, Runtime, Probe and shared-files lines, rules table (item 2) | first response, after Scan; then the one question |
| Instrument | Workflow steps 2 to 4, one line per service | when wiring starts; then one line at each service boundary (Hard rule 10); with six or more services, one per batch of 3 to 4 instead, or every 2 minutes |
| Verify | the one batched ask through `verify.sh ask`, per service and signal, in its `--env` scope | with the fresh-window offer when the window was blocked; otherwise at the top of the Handover message, right above the Handover block |
| Handover | closing summary, fixed shape | last |

A moment is announced when it starts. Scan, Instrument and Verify take minutes, and tool
calls scrolling by do not tell the developer the run has begun. Each of the three has a
start in `assets/terminal.md`, printed as text: one line saying what begins and roughly how
long, under the stepper line for Scan and Instrument. Scan's start comes right after the
steps above, before the first read of the repository; Instrument's is the first text after
the one question is answered (none after "Stop here"); Verify's is the text right before
the first app or service starts, one line covering every service. The rest of the block
prints when the work is done. Each moment's stepper line prints once, at one point: Scan's
and Instrument's at their starts, Plan's and Handover's at the top of their blocks, and
Verify's at the top of its Done block, once per verification window. Scan's and
Instrument's Done parts and Verify's start carry none. A start left out fails this variant,
like a block left out.

The terminal shows nothing while a call runs. Before any call you expect to take more than
about a minute (an install, a build, starting the app, the settle, the batched ask), print
one line saying what it waits on and roughly how long; Verify's start is that line for the
starts, the traffic, the settle and the batched ask. Scan's first tool calls go out in one
turn: the git state, the runtime probe, the build-stage read, the deploy census, and the listing and
manifest reads. The telemetry probe follows in the next turn, with the unit directories that listing
gave.

Verify is left out only when the run started nothing (wiring only, no runtime, declined, no
header); Handover's stepper then shows `[– Verify]`.

## Asking

Ask where the hub asks, and nowhere else: the one question (Plan); the run offer when the
question did not grant the run; the header question of Workflow step 4; the fresh-window
offer after a blocked window (Verify); the hub's conditional asks (a file the plan did not
name, a log bridge over personal data, a file edited since the plan on resume); and at
Handover, "Done" or "Open a PR". The hub's leftovers offer rides in the Handover call when it applies. A question the request already answered is not asked; a named level or asking to instrument, wire, run or verify answers none (hub step 3). A
moment without an ask shows its block and moves on.

Each ask is one `AskUserQuestion` call: 2 to 4 options, the hub's recommended one first
and marked "(Recommended)", each other option an alternative the hub text allows. The one
question is one call carrying up to three questions:

| header | options |
|---|---|
| Scope | "All N in-scope services (Recommended)", "Pick runtime groups" (then a multi-select, one option per runtime, at most 4, the rest folded into one); left out when one service is in scope |
| Level | "Level 3 (Recommended)", "Level 2", "Level 1", each description the level written out as the hub writes it |
| Run | "Approve and run (Recommended)", "Approve, I start the app myself", "Stop here"; the Runtime line narrows it as `../bluebox-otel-instrumentation/references/probes.md` says: no usable runtime or an unreachable registry leaves "Approve, wiring only (Recommended)" and "Stop here", a daemon that is down leaves "Approve, I start the app myself (Recommended)" and "Stop here" |

"Stop here" ends the run before any file change; every in-scope service closes
`user_declined`. The header question's text is the one message of
`../bluebox-otel-instrumentation/references/export-contract.md` § Header precondition, its
options "Done" and "Skip". The fresh-window offer is "Run a fresh window
(Recommended)" and "Continue to Handover".

Print the moment's block in full as text before its ask: the hub's order rule puts the
plan and rules tables on screen before the one question, and the transcript is the run's
record. The terminal may fold that text into one line, but never a question's own text, so
the `question` field of the call's first question repeats the essentials as a compact
panel: line 1 the moment and its strip (`Plan · step 2 of 5 · 1 service · env
docker-compose · expected 13–20 min`), a blank line, one line per service (at most 4, then
`+N more`), one `⚠︎` line per thing the developer must act on and per finding, a blank
line, then the question. The call's other questions keep a one-line text. Tables and `ℹ`
lines stay in the block.

Without `AskUserQuestion`, ask the same options as a numbered list per question, then stop
and wait for the reply. A dismissed or canceled question is not an answer. With no
interactive user, take the hub's headless path: every block still prints, no question is
asked, and the run ends at the closing summary. A guided run is asked for by a person, so
do not conclude from how the session looks that nobody is there. The headless path needs
the hub's one sign: the request says the run is unattended. `AskUserQuestion` refusing the
call or failing to deliver it is no sign: ask the numbered list instead, which ends the
turn, and a run nobody answers stops there, after the plan, with no file changed.

## The run file

`.bluebox/instrumentation-run.md` is the hub's readable record
(`../bluebox-otel-instrumentation/references/state-resume.md` § The readable record): the
hub's `state-update.py` renders it at every call in the shape of
[assets/run.md](assets/run.md), and you never write it yourself. Pass each moment's block,
without its stepper line and strip, as that step's report with `--step` when it prints
(Instrument: the files you changed as the asset's File | Change table, since the script
renders the service table), and each answer with `--decision`, as that section shows. The first calls come right after the
one question is answered, never before (the hub's order rule allows no file before that
answer): the Scan block, then the Plan block with that answer. It sits beside the hub's
`.bluebox/instrumentation-run.json` and never replaces it.

## Handover

The Handover block is the closing summary in the hub's fixed shape, then the files you
changed, the names of the env vars the developer supplies and the hub's build leftovers line, if any. Ask "Done" (recommended) or "Open a PR",
then, in this order:

1. Pass the answer as the last decision: that render is the finished run file, every
   progress glyph ✓ (`–` for a moment left out).
2. Open a PR follows the hub: that finished run file becomes `docs/otel-instrumentation.md`,
   committed with the code, and its Handover section is the PR body. Done leaves the
   changes uncommitted.
3. One line: the PR URL, or where the changes and the run file are.
