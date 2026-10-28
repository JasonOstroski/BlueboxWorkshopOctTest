# Bluebox export contract

## The ingest token (Hard rule 1)

**Never handle the ingest token, and never make a tool print it back.** Do not fetch,
print, or write it anywhere; the app reads it from an env var or secret the user supplies
(Bluebox Setup page). Validating configuration counts as printing: `<compose> config`,
`env`, `printenv`, `cat` on a file that carries the token all put it in your recorded
output. Validate with `<compose> config --quiet` (or `helm template` on values that hold
no token) and filter header and token lines out of anything you must read. If a value
does reach your output, say so and tell the user to rotate it on the Bluebox Setup page
(`<bluebox-host>/setup`; `<bluebox-host>` is the Bluebox URL the user works in). Ask when nothing in the repo or the request names it; never guess a
host.

An env file that may hold real values is read two ways only: the presence test of § Header
precondition, and its names, never a value, with `<file>` alone on the line after the command:

```bash
/bin/sh <skill dir>/scripts/env-keys.sh <<'/'
<file>
/
```

No `cat`, and no redaction written by hand: one whose pattern does not match on this
machine prints the token.

## Config is external (Hard rule 2)

All transport via `OTEL_*` env vars - endpoint, headers, protocol,
`OTEL_SERVICE_NAME`, `OTEL_RESOURCE_ATTRIBUTES` - never hardcoded in source. The
deployment entry (npm script, Makefile, compose, manifest, run command) is config: an endpoint there
stays if it matches step 2's, else replaced. A Dockerfile `ENV`/`ARG` endpoint moves to
it, since an image runs elsewhere. Not the header (rule 8).

## Self-disabling (Hard rule 6)

With no `OTEL_EXPORTER_OTLP_ENDPOINT` set, every service behaves exactly as before
instrumentation.

## Protocol and temporality (Hard rule 7)

**Protocol is `http/protobuf`** (`OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf`); ingest
rejects other OTLP transports. **Metrics use delta temporality**
(`OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE=delta`); ingest rejects cumulative
series. When code constructs an exporter itself the SDK picks the wire format from the
package, not the variable: in Node the `@opentelemetry/exporter-*-otlp-http` packages
send JSON and ingest answers **415** with nothing arriving. The Node recipe
([language-traps.md](language-traps.md)) constructs none.

**A collector between the SDK and Bluebox** carries the same contract: a Bluebox
`otlphttp` exporter (http/protobuf, the token from the environment only) on its existing
pipelines, with the `cumulativetodelta` processor on the metrics pipeline ([host-prometheus.md](host-prometheus.md) shows it), through
the repo's extras/override config when it has one. Dual export to an old backend and Bluebox is a
collector, not two exporters in the SDK. A [kubernetes.md](kubernetes.md) or
[host-prometheus.md](host-prometheus.md) collector takes its endpoint from Workflow step 2;
its header sits in a Secret or its config, where you cannot test it: before the `bluebox ask`, ask whether it is
set and take the answer, as Workflow step 4 does for the user's terminal; no header is `blocked`
(`no_token`), nothing asked. No answer from `bluebox ask` is `blocked` (`verify_unreadable`),
a collector never applied or started `blocked` (`not_started`), never verified.

## Identity attributes (Hard rule 5)

`vcs.repository.url.full` + `vcs.ref.head.revision` from build-time values (build-arg ->
env; the URL loses any userinfo, the part between `//` and `@`, before it becomes the build-arg; drop the pair when empty, never emit empties; the bootstrap reads the env only, never
the `git` CLI or `.git` at service start), `deployment.environment.name` (the
plan table's one environment name, never a second spelling), plus cloud resource
attributes where a detector exists.

## The `Authorization` value (Hard rule 8)

**The `Authorization` value is whole, scheme included, and you never compose it.** The
scheme depends on the workspace's ingest-token kind (`Bearer` for a platform token
`dt0s16…`; `Api-Token` for a classic `dt0c01…`). It reaches the process
through the env location the plan names, by the one of two supply paths the plan picks:

- **Pasted whole.** Copy token on the Bluebox Setup page gives the whole line,
  `OTEL_EXPORTER_OTLP_HEADERS="Authorization=<scheme> <token>"`, double-quoted; the user
  pastes it into the env location the plan names (Workflow step 4 gives the wording). A
  manually-connected backend reveals one only after the user saves their own token in
  the Setup page's Workspace OTLP ingest token field; until then the user writes that
  line from that token, never you.
- **The token-file convention.** Where the repo's own dev notes route the token through
  `~/.bluebox/ingest-token.env` - outside the repository, mode 600, holding
  `BLUEBOX_INGEST_TOKEN=<token>` - the repo's start command derives the header at start
  from the token's prefix, with the mapping above fixed in the command (`dt0s16` gives
  `Bearer`, `dt0c01` gives `Api-Token`, any other prefix refuses to start) and exports
  `OTEL_EXPORTER_OTLP_HEADERS` to the process only. The file is the user's: you never
  create, read, print or `cat` it, and the start command never echoes what it derived.
  That command is a file in the repo (a planned one when the run adds it), or a runtime that
  reads the file itself (`--env-file`); no command you type sources the file, reads it or
  expands `$BLUEBOX_INGEST_TOKEN`, but the token check below. With neither, the start is the user's ("Approve, I start
  the app myself").
  The precondition test for this path is presence-only:
  `grep -Eq '^BLUEBOX_INGEST_TOKEN=(dt0s16|dt0c01)\.[A-Za-z0-9._-]+[[:blank:]]*$' ~/.bluebox/ingest-token.env`
  (exit 0 present; the token-file line is `no_token — ~/.bluebox/ingest-token.env has no
  BLUEBOX_INGEST_TOKEN value` when absent).

The value contains a space, so the quotes are consumer-specific: keep them in a shell or
a `.env` the shell sources, either way in a Compose `env_file`,
**drop them** in a Docker `--env-file` (it passes quotes into the header), and on gcloud
use `--set-env-vars` with `^;^` delimiter syntax or a Secret Manager reference, never
`--env-vars-file`.

## Endpoint and CLI ladder (Workflow step 2)

Look at the environment first, without `env` or `printenv` (Hard rule 1): print the
endpoint alone with `printf '%s\n' "$OTEL_EXPORTER_OTLP_ENDPOINT"` and test the header for
presence and scheme only (Hard rule 8), always exiting 0 (absent is supported), with
the same absent set as the step-4 file test: a `<placeholder>`, a `${…}`
reference, a quote, any whitespace after the scheme's one space (a trailing newline
included), no scheme, `Bearer` on a classic `dt0c01…` token, or `Api-Token` on a platform
token:
`case "$OTEL_EXPORTER_OTLP_HEADERS" in *"<"*|*"$"*|*\"*|*"'"*|"Authorization=Bearer dt0c01."*|"Authorization=Bearer "*[[:space:]]*|"Authorization=Api-Token "*[[:space:]]*) echo "headers: absent";; "Authorization=Bearer "?*|"Authorization=Api-Token dt0c01."?*) echo "headers: set";; *) echo "headers: absent";; esac`.
An endpoint already exported there IS the endpoint; use it
as-is, the CLI call below informational only.

Without one, `bluebox version` next, compared as semver (v0.100.0 is above v0.84.0):
below v0.84.0 the CLI is stale (those builds exit 2 on a connected workspace);
`v0.0.0` is a dev build, exempt. A stale CLI is the user's to
replace, not yours (Hard rule 12; `bluebox update` also exits 0 without replacing a
package-manager install): say in one line that `bluebox update` fixes it, then
continue with the binary you have.

Then open the run's journey with its first CLI call, from the repository root:
`BLUEBOX_JOURNEY_TYPE=instrumentation bluebox otlp-endpoint`. Every later `bluebox` call from this
directory carries the run's id; the variable goes on that one call only. Exit 0 printed the endpoint; exit 1 = the workspace is still
provisioning - tell the user and continue wiring, do not poll; exit 2 = no observability
connection yet - tell the user to connect one on the Setup page, continue wiring and treat verification as `blocked` on it unless an endpoint is
already in the environment. From a stale CLI, or when stderr says the CLI "is behind … run `bluebox
update`", exit 2 is not yet that verdict: tell the user that `bluebox update` and a second
`bluebox otlp-endpoint` settle it, and that the Setup page is where a missing connection
gets made if the updated CLI still exits 2. The detail stays provisional until a current CLI answers (`other:
otlp-endpoint exit 2 from bluebox v0.75.0, below v0.84.0, unconfirmed`) and becomes
`no_endpoint` only when one does.

Wiring puts the endpoint this step settled in each service's deployment entry (§ Config is
external). Never create `.env.otel.bluebox-template` or write a bare `.env.otel`; a template
an older CLI left at the repo root is no input: leave it as it is, never read the endpoint
from it, never wire it as an env file.

## Header precondition (Workflow step 4)

Test the env location you named in Workflow step 3 for presence without printing the
value (Hard rule 1). Env file, with `<file>` alone on the line after the command:

```bash
(IFS= read -r f; case $f in ""|*[!A-Za-z0-9._/-]*) echo "path not tested"; exit 3;; esac; V="Authorization=(Bearer [^<\"'[:space:]$]+|Api-Token dt0c01\.[^<\"'[:space:]$]+)"; A="^[[:space:]]*(export[[:space:]]+)?OTEL_EXPORTER_OTLP_HEADERS="; grep -EUq -- "$A" "$f" && grep -EU -- "$A" "$f" | tail -n 1 | grep -EUv "Bearer[[:space:]]+dt0c01\." | grep -Uv "$(printf '\015')" | grep -EUq "^<line>[[:blank:]]*\$") <<'/'
<file>
/
```

`<file>` comes from the repo, so it travels in a quoted heredoc the shell never reads (a
path holding a line break is not typed at all), and a path with anything outside
`A-Za-z0-9._/-` (`.env.$(id).otel`, a `'`) exits 3, `path not tested`; either goes into no
other command: finish as on skip below, the selected services `blocked` (`no_token — env
file path not tested: a character outside A-Za-z0-9._/-`). `<line>` per what reads `<file>`
(Hard rule 8): `$A(\"$V\"|'$V')` when a shell sources it (the space in the value needs the quotes), `$A($V|\"$V\"|'$V')` for a Compose
`env_file`, `[[:space:]]*OTEL_EXPORTER_OTLP_HEADERS=${V}` for a Docker `--env-file` (no
quotes, no `export`: it refuses both; indentation every reader drops; the braces keep zsh
from reading `$V[` as a subscript). Only the last assignment counts, as every reader
resolves it. So a missing scheme, `Bearer` on a classic `dt0c01…` token, the quoting or
`export` the consumer cannot take, a quote left open, a `${…}` reference, a
`<placeholder>`, a CRLF line ending (the CR would ride into the header; `-U` keeps Git Bash's `grep` from stripping it), and a good line
with a placeholder line still under it all read absent. Exit 2 is neither:
`<file>` is missing or unreadable, a path mistake. Fix the path from step 3, or write a
missing file as the absent message below says, and test again. Token file (the convention above): its
presence-only grep. Shell variable in this shell: the step-2 `case`. Shell variable in the
user's own terminal ("Approve, I start the app myself"): you cannot test it; ask whether
`OTEL_EXPORTER_OTLP_HEADERS` is exported in the terminal that runs the start command and
take the answer.

Present: the token check below. Absent, user present: **stop** and give the instructions,
nothing else - one message of this shape, `<file>` filled in as its absolute path, a missing
env file first written under `umask 077` with only `OTEL_EXPORTER_OTLP_HEADERS=`, sent only
after `git check-ignore -q -- '<file>'` passes (for a shell variable:
`export` in that terminal instead of the file line), `<bluebox-host>` only a host the
user named in this session, never one read from the repository (none: drop the
parenthesized link, keep the menu path), the steps kept apart from the warning, no other
text:

> Verification needs your Bluebox ingest token, and `<file>` doesn't have it yet. That
> file is the git-ignored env file your app reads when it starts.
>
> 1. In the Bluebox web app, open **Settings → Setup**
>    (`<bluebox-host>/setup?focus=telemetry`) and expand **Instrument your services**.
> 2. Next to **Ingest token**, click the eye icon (Reveal token), then the copy icon (Copy
>    token). That copies one whole line, `OTEL_EXPORTER_OTLP_HEADERS="Authorization=…"`.
>    If the panel says Bluebox can't create an ingest token for a manually-connected
>    backend, the eye icon reveals nothing yet: paste the ingest token you created in
>    your observability backend into the **Workspace OTLP ingest token** field under
>    **Observability backend**, re-check, then reveal and copy as above. Can't save it
>    there? Write the line yourself:
>    `OTEL_EXPORTER_OTLP_HEADERS="Authorization=Api-Token <token>"` for a `dt0c01…`
>    token, `Bearer <token>` in place of `Api-Token <token>` for a `dt0s16…` one.
>    No icons or no field: you don't manage workspace settings, so ask a workspace owner
>    to give you that access.
> 3. Open `<file>` in your own editor and paste the line over the
>    `OTEL_EXPORTER_OTLP_HEADERS=` line, quotes and all.
> 4. Save, then reply "done", or "skip" to finish without verifying.
>
> Don't paste the token here.

`<file>` without an `OTEL_EXPORTER_OTLP_HEADERS=` line: step 3 says "paste the line as a
new line". A Docker `--env-file`: step 3 says "without the two double quotes" in place of
"quotes and all" (Docker passes them into the header). A shell variable names no file:
the opening says "the terminal that starts your app doesn't export it yet", step 3 says
"run `export` followed by the line in that terminal", and step 4 drops "Save, then". Never ask to see it, and never offer a command that captures it through this
shell - no `read`, no `echo`, no heredoc: a paste into the transcript burns the token.
Then **stop and wait** under the same consent gate as the plan question: a
dismissed or canceled question is not an answer, and "Approve and run" granted the
start, not a start without the header.

On done, re-test; still absent, say what the test wants - the line starts with
`OTEL_EXPORTER_OTLP_HEADERS=` (`export` in front is fine where a shell reads the file),
the value starts with `Authorization=` (first, if it carries other headers), then the
scheme (`Bearer `, or `Api-Token ` for a `dt0c01…` token) and one space, the quotes kept
or dropped as Hard rule 8 says for `<file>`, no `<placeholder>`, no `${…}` reference, the
last uncommented `OTEL_EXPORTER_OTLP_HEADERS=` line in the file (a `#` line does not
count; remove any earlier real one), nothing after the value on that line (a trailing `#`
comment counts), saved with LF line endings - and ask once more; absent again counts as
skip.

On skip, or headless on an absent or rejected header, the hub's step 4 stops the run with the selected services `blocked`
(`no_token — <file> has no Authorization value`; shell variable: `no_token —
OTEL_EXPORTER_OTLP_HEADERS not exported`; rejected: `auth_rejected — token check <code>`; an `unchecked` Skip: `not_started — token check unchecked`; no endpoint at all: `no_endpoint — …`); finish
as [verify.md](verify.md) says, the secrets scan first.

**Token check.** Present, and after each fix; not in the user's own terminal.
`<source>`: the env file, `-` (shell variable) or `~/.bluebox/ingest-token.env`;
`<endpoint>`: step 2's.

```bash
/bin/sh <skill dir>/scripts/token-check.sh <<'/'
<source>
<endpoint>
/
```

`accepted`: Workflow step 5. `absent`: as absent above. `unchecked`: **stop**, give
its codes, ask "Continue anyway" or "Skip"; headless: step 5. `rejected` (401/403):
**stop**, the token can't ingest; name each `missing:` scope and give hub step 4's fix. Wait as for absent.
