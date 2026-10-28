# Terminal blocks for the five moments. Markdown only, no HTML: the terminal prints tags
# literally. Fill {{tokens}}, repeat a table row per item, drop a line whose value is empty.
# Each moment's stepper line prints once: Scan's and Instrument's at their start, Plan's and
# Handover's at the top of their block, Verify's at the top of its Done block, once per
# window. Scan's and Instrument's Done parts and Verify's start carry none. A start is one
# line of what begins, printed where the section says; the rest follows when the work is done.
# A {{hub: ...}} slot is the hub's own table or
# line, in the hub's shape: a block frames the hub's output, it never replaces it.
# Glyphs: "⚠︎ " is U+26A0 U+FE0E and one space (the plain U+26A0 is drawn two cells wide and
# swallows the space); "ℹ " keeps its space too. ⚠︎ marks only what the developer must act
# on, or a finding (a behavior change, a mismatch, an unverified signal); ℹ what is handled.

## scan

Start, before the first read or probe of the repository:

`[● Scan]  [ Plan]  [ Instrument]  [ Verify]  [ Handover]`

Reading the repository, read-only: about 2 minutes.

Done, no stepper line:

**{{repo}} @ {{revision}}** · {{n_components}} components · {{n_in_scope}} in scope · {{n_excluded}} excluded

**Runtime** {{hub: the Runtime line}}

| Service | Language | Telemetry today |
|---|---|---|
| {{service}} | {{language}} | {{telemetry_today}} |

**Excluded ({{n_excluded}})**

| Component | Why |
|---|---|
| {{component}} | {{reason}} |

No question: Plan follows in the same response.

## plan

`[✓ Scan]  [● Plan]  [ Instrument]  [ Verify]  [ Handover]`

**{{n_in_scope}} services · env `{{env}}` · expected {{low}}–{{high}} min**

{{hub: the plan table}}

{{hub: the per-runtime legend, then the Expected, Runtime, Probe and shared-files lines}}

{{hub: the rules table}}

**Prerequisites**
- ✓ {{satisfied}}
- ⚠︎ {{developer_must_act_before_verify}}
- ✗ {{blocks_the_run}}
- ℹ {{already_handled}}

Prerequisites come from what Scan read and from the hub's plan lines: run nothing to fill
them. The ingest header is the hub's to test, at its Workflow steps 2 and 4, after the
question is answered, never before it.

After the Scan and Plan blocks are printed in full, one call with the Scope, Level and Run
questions. The first one's `question` field is this panel; the others keep one line:

    Plan · step 2 of 5 · {{n_in_scope}} services · env {{env}} · expected {{low}}–{{high}} min

    {{service}} — {{language}}, {{recipe}}
    ⚠︎ {{developer_must_act}}

    {{the first question}}

## instrument

Start, as the first text after the one question is answered (with no question asked, right
after the Plan block), before any file changes; none after "Stop here":

`[✓ Scan]  [✓ Plan]  [● Instrument]  [ Verify]  [ Handover]`

Wiring {{n_chosen_services}} services: about {{minutes}} minutes.

At each service boundary, one line, no stepper line: the service, its state and what comes
next, as `{{service}} wired and build-verified ({{n_done}} of {{n_chosen_services}}); {{next}}.`
With six or more services, one line per batch of 3 to 4 instead, or every 2 minutes. A blocked
service's line opens with its reason token.
No question unless the hub asks one here (a file the plan did not name, a log bridge over
personal data, the run offer, the header question).

## verify

Start, as text right before the first app or service starts, one line covering
every service; no stepper line:

Starting {{n_started}} service(s), sending traffic, then asking Bluebox what arrived: about {{minutes}} minutes.

Done, with the fresh-window offer when the window was blocked; otherwise at the top of the
Handover message, right above the Handover block. Once the app ran, it is never left out,
and it opens with Verify's one stepper line:

`[✓ Scan]  [✓ Plan]  [✓ Instrument]  [● Verify]  [ Handover]`

**Reporting {{n_reporting}} of {{n_started}} · `--env {{env}}` · window {{t1}}–{{t2}} · attempt {{n_attempts}}**

| Service | Spans | Metrics | Logs | State |
|---|---|---|---|---|
| {{service}} | {{spans}} | {{metrics}} | {{logs}} | {{state}} |

A cell is the count the batched ask returned in that scope, `–` for a signal outside the
level, or `⚠︎ none` with one line under the table saying why. State is `reporting`, or
`blocked` with its reason token.
**Identity** `vcs.repository.url.full` {{value_the_ask_returned}}

Question only after a blocked window (the fresh-window offer): "Run a fresh window
(Recommended)" · "Continue to Handover". Its `question` field is the strip, then one line
per ⚠︎ reason, then the question.

## handover

`[✓ Scan]  [✓ Plan]  [✓ Instrument]  [✓ Verify]  [● Handover]`

**{{n_reporting}} reporting · {{n_blocked}} blocked · {{n_skipped}} skipped · {{n_files}} files ({{lines}}) · secret scan {{secret_scan}} · app {{app_state}}**

{{hub: the closing summary: the Time to first telemetry line, the table, the "Verified locally only" line when the record says local, the target table when it lists deploy targets, Limitations, Next steps}}

| File | Change |
|---|---|
| `{{file}}` | {{change}} |

**You supply (names only)** `{{env_var}}` — {{note}}

{{hub: the build leftovers line, when its report printed one}}

The question's `question` field: `Handover · step 5 of 5 ·` and the strip, one line per
changed file (at most 8, then `+N more`), `You supply: {{env_var_names}}`, one line per
limitation or finding, then "What next?". Options: "Done (Recommended)" · "Open a PR".
When the leftovers line counts any, the same call carries the hub's second question (closing-summary.md § Handover): "Keep (Recommended)" · "Remove".
