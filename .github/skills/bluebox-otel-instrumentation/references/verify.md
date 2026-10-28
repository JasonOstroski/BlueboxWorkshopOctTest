# Run it, then verify

`scripts/verify.sh` runs this
file's two commands with their guards built in
(`bash <skill dir>/scripts/verify.sh logs …` for the exporter read, `… ask …` for the
batched check; `--help` prints the arguments), always through `bash`.

## The run offer

If the question did not grant the run, offer
it after wiring and build-verify: name the start command from the inventory, say what it
will do - start the stack, send one request to each instrumented service (through the
reverse proxy where there is one), settle, verify once - and ask
before starting anything.

If the user declines, or no user is present and you cannot start the stack, stop there:
those services are `blocked`, their detail opening with `not_started —` when the developer
declined or starts it, else with the one reason-set token that stopped you (`no_token`, `no_endpoint`, …),
followed by the runnable command, secrets replaced by placeholders (`--env-file <file>`, `$DT_TOKEN`),
and next steps repeats it. For `not_started`, it adds the `verify.sh ask` line below,
filled in under its quoting rule, and offers that run minus the start once the developer says the app is up. Do not verify an app that is not running.

A containerized stack on a host whose probe found no usable runtime has no run and no
verification: skip this section without looking for a runtime
(Hard rule 12). Those services are `blocked` (`no_runtime — no docker, podman or nerdctl
daemon reachable; start or install one, then the plan's start command`), and Next steps carries
that start command plus the verification command. `build_failed` is for a build that ran.
Services the reachability line closed `registry_unreachable` or `endpoint_unreachable`
(Workflow step 1) skip this section the same way, whatever the question granted.

## Start and stop

Learn a service's flags, port and start command from its source, README or Makefile, never
by executing it. Every run of it, a probe included, is the start below.

Before the start, check the port the app will bind: `lsof -ti tcp:<port> -sTCP:LISTEN`
(`<port>` digits only) prints nothing when it is free. A bound port gets the next free one
(Workflow step 5), never a kill - not even a kill-by-port recipe in the repository's own
notes. Start the app in the background with its output in a fresh temporary file,
`L=$(mktemp); <start command> > "$L" 2>&1 & echo "pid $! log $L"`, and keep
`<start pid>` and `<log path>`: the
exporter read below tails that log, and a file the repository placed (a `.bluebox` symlink,
say) never takes the output. A restart writes to the same file,
`<start command> > '<log path>' 2>&1 & echo "pid $!"`. When a
wrapper starts the server (`make run`, `go run`,
`npm start`), that number is the wrapper's: wait for the port, `<port>` alone on the line after the command,

```bash
timeout 120 sh -c 'IFS= read -r p; case $p in ""|*[!0-9]*) exit 2;; esac; until lsof -ti "tcp:$p" -sTCP:LISTEN >/dev/null; do sleep 2; done' <<'/'
<port>
/
```

then take the server's PID from the same `lsof` line. With a wrapper or without, keep the
server's start time and executable name, `ps -o lstart=,comm= -p <pid>` (never `command=` or
`args=`: a start command's arguments can carry the ingest token, Hard rule 1). Stop or restart by that PID alone, and only while it is still
yours: digits only and above 1, `lsof -nP -a -p <pid> -iTCP:<port> -sTCP:LISTEN` still
lists it, and `ps -o lstart=,comm= -p <pid>` still prints exactly what you kept; otherwise skip it and say so. The stop is `kill <pid>`. A restart first waits for it and `<start pid>` (the wrapper,
when one started the server) to exit,
`timeout 60 sh -c 'while kill -0 <pid> 2>/dev/null || kill -0 <start pid> 2>/dev/null; do sleep 1; done'`;
one still running after that is reported, not
restarted. A PID the run lost is not looked up again: say the process is still running. Before
`<compose> up`, keep what `<compose> ps -q` prints: nothing means the stack is the run's,
and `<compose> down` stops it; otherwise stop only the containers whose IDs were not in that
list, by ID (`<runtime> stop <id>`, the runtime the probe found), and leave the rest.
Once the app is stopped for good, or its PID is lost, delete that log
(`rm -f -- '<log path>'`, the path mktemp printed).

## Read the exporter before you wait

Workflow step 5's verification start carries the language's diagnostics switch (the table in
[language-traps.md](language-traps.md)), set like that step's export knobs, per service: prepended to the one-off start command (`OTEL_LOG_LEVEL=info
OTEL_METRIC_EXPORT_INTERVAL=10000 … <start command>`) or added next to the knobs in the
same throw-away compose `environment` (that start only).
After the one request per service, read the export lines before any wait.

Read the lines ~20 s after the request with
a bounded wait (Hard rule 11), and never the whole log: grep the status lines and
drop anything that could carry a header, cut the query string and user-info out of any URL
left and mask a Dynatrace token and an Authorization, Api-Token, Bearer, Basic or OTLP
headers value as `scripts/state-update.py` would refuse it (Hard rule 1). `bash <skill dir>/scripts/verify.sh logs
--lang <language> --service '<name>' --compose "<compose>"` is that read (a service name the
ask's rule below refuses goes into no command, the service `blocked` the same way): it runs
`<compose> logs --since 2m '<service>' 2>&1 | grep -ai <grep> | grep -viE 'authorization|header'`
with the row's `-e` list from the diagnostics table in place of `<grep>` and pipes the result
through its `mask` sed filter; pass `--logs-cmd '<command>'` instead of `--compose` for `kubectl logs`,
a journal or the process's stderr on a stack that is not compose, each name in it held to the ask's rule below, `@` allowed. `--logs-cmd` refuses `*`, so read a .NET log directory there with `grep -rh "" -- <dir>`. A failure line that
mentions a header is never shown, only counted (`<N> failure line(s) … withheld`): the
transport is not confirmed, so take it as the 401 or 403 row below. An empty read
is evidence only when the log command itself succeeded: `verify.sh` runs it once and exits
2 when it fails (by hand: once without the greps, both streams discarded,
`<compose> logs --since 2m '<service>' >/dev/null 2>&1`, the .NET `exec … cat` the same way,
never printing the file), and that failure is a run
problem to fix, never a clean transport and never `signal_unwired`. Then map what you
read, per service and per selected signal:

| the log says | it means | do, then restart and read again |
|---|---|---|
| no failure line after two export intervals | the transport is right | go to the settle wait |
| 401 or 403 (`Unauthorized`, `Forbidden`) | the `Authorization` value or its scheme (Hard rule 8) - never print it: re-test presence with the step 4 grep and have the user paste the whole value again | still rejected → `auth_rejected` |
| 415 (`Unsupported Media Type`) | JSON on the wire where ingest takes `http/protobuf` only (Hard rule 7): a JSON protocol setting, an exporter the code constructs | set the protocol to `http/protobuf` everywhere it is set, or construct no exporter and let the variable choose; restart or rebuild; still 415 → `wire_rejected` |
| 404 (`Not Found`) | the endpoint path: the value is not what step 2 printed (a per-signal URL in the generic variable, `/v1/<signal>` already appended) | set it verbatim; still 404 → `endpoint_rejected` |
| name resolution failed (`ENOTFOUND`, `UnknownHostException`, `no such host`) | the endpoint host: the value is not what step 2 printed | set it verbatim; still failing → `endpoint_rejected` |
| connection refused or timed out on the host step 2 printed | the network, not the config | `egress_blocked`, naming host and port in the detail |
| nothing registers a provider, reader or bridge for a selected signal (the Java agent and `NodeSDK` wire every signal not set to `none`), or an SDK exception (`{"stack":…}`) | that signal is not wired: no metrics reader, no log bridge, no provider | back to Workflow step 3 for that signal; still absent → `signal_unwired` |

Fix, restart, read again before any settle wait: a retry after a fix starts at the log read,
never at the ask. The ask runs once, after every selected signal
of every selected service shows no failure line or carries the token that stops it, and a
signal the code shows as unwired is not a verifier miss to re-ask for. If the repo's
committed run command picked up the switch or the knobs, take them out before the closing
summary.

## Settle, then ONE batched ask

With no failure line left for any selected signal, run ONE batched check with `--settle` 45 when the export
knobs of Workflow step 5 are set and no logs are in scope, 90 otherwise: the script waits, ends the window
and asks, so run no sleep or wait loop of your own. It covers every selected service and only the
selected signals, minus per-service drops under Hard rule 4, through the skill's own script, not a
hand-typed `bluebox ask` (the follow-up below excepted). `<T1>` is the traffic start, never narrowed
to the burst.

```bash
bash <skill dir>/scripts/verify.sh ask --env '<env>' --window '<T1>..<now>' --services '<service list>' --signals '<the signals the user selected>' --settle '<seconds>'
```

It takes minutes: give the call a Bash `timeout` of at least 600000 ms, in the
foreground (Hard rule 11); a timed-out call is a lost answer, not a reason to poll. Every value
goes in single quotes; the rule below guards the command you type (the script itself
checks only `--env`). A value with a character outside `A-Za-z0-9._/:+-`, the comma and the space is
never put in the command: a service whose name fails stays out of the ask, `blocked`
(`other: service name not typed into a command`), and an environment name that fails keeps
the ask from running at all, every service `blocked` the same way (`other: environment name
not typed into the ask`). The script sends this prompt through `bluebox ask --env <env>`, and
it is what you judge the answer against:

```text
For the window <T1>..<now>: which of these services have <the
signals the user selected — e.g. spans, logs, and metrics> arriving — <service list>?
Count by OTLP service.name, not by entity. For metrics: FIRST list every metric key that
carries that service.name in the window (the catalog for that service - do not test guessed
key names or prefixes), then judge from that list; any key the app exported counts -
request, client-side (http.client.*), runtime, JVM - but list dt.* and other entity-derived
keys separately and do not count them: dt.service.request.count/failure_count/response_time
are derived from spans and exist for every service with inbound request spans. List
per-service signals, the metric keys seen, and the values of vcs.repository.url.full on
their spans.
```

`<env>` is the plan table's environment name, the `deployment.environment.name` every
service exports. The run record carries it (state-resume.md):
run the script from the repository root and leave `--env` out, or pass that same name; a
different one is refused, and a name another setting suggests (an
`ENVIRONMENT=` variable, a code default) is not a reason to switch, since
`OTEL_RESOURCE_ATTRIBUTES` decides what the services export. The closing summary reports this scoped
ask's counts, each naming its scope (`--env <env>`): an unscoped `bluebox ask` counts
across every environment.

Only the window's own answer confirms a signal: a 24 h catalog, a widened answer or an
earlier run's keys prove nothing about this run. A selected signal the window shows 0 for
gets the one follow-up below, then `blocked` (`verify_absent — 0 <signal> in the window`),
never `reporting`.

Spans present but "metrics absent" is usually a verifier miss when the log showed no metrics export
failure; where nothing registers a metrics reader it is `signal_unwired`, not a miss. The one allowed
follow-up ask names the expected keys for the missing services;
what is still missing is `blocked` (`verify_absent —` with the evidence you have); do not
loop. Derived `dt.*` keys
never fill that gap: at level 2 or 3, a service with spans and only derived keys after the
follow-up is `blocked` (`verify_absent — only derived dt.service.* keys`), never
`reporting`. A `vcs.*` mismatch
is a warning when the signal arrived.

## Metric keys per runtime

At level 2 or 3, "metrics arriving" means the keys the runtime's HTTP instrumentation emits,
the older or stable semconv name:
- Node (`@opentelemetry/instrumentation-http`): `http.server.duration`, `http.client.duration`
  (`http.server.request.duration`, `http.client.request.duration` with
  `OTEL_SEMCONV_STABILITY_OPT_IN=http`)
- Java agent 2.x: `http.server.request.duration`, `http.client.request.duration`, `jvm.*`
- .NET auto-instrumentation: `http.server.request.duration`, `http.client.request.duration`
- Go `otelhttp`: `http.server.request.duration` (`http.server.duration` on older contrib lines)
- Python `opentelemetry-instrument`: `http.server.duration`, `http.client.duration`
  (`http.server.request.duration`, `http.client.request.duration` with the same opt-in)

## Before finishing

Scan tracked changes for secrets (`dt0c01.`/`dt0s16.` prefixes, real
`OTEL_EXPORTER_OTLP_HEADERS` values, userinfo-bearing URLs), then stop and remove what you
started. Record the verification table, window and attempts as `--step verify`
with `--verified-scope` ([state-resume.md](state-resume.md)). If the first window was blocked, offer the run again for a fresh one. Then the
closing summary ([closing-summary.md](closing-summary.md)).
