# Language traps and recipes

Per-runtime knowledge: the first two sections bind the plan table, the rest wiring and
Workflow step 5.

## Zero-code first, and never twice (Hard rule 3)

Prefer the language's zero-code auto-instrumentation (Java agent, .NET auto-instr,
`node --require` + auto-instrumentations, `opentelemetry-instrument`) and add code only
where the runtime needs it (Go, C++, bespoke frameworks); before an SDK recipe, confirm in
the OTel registry that no library covers
the framework, HTTP client and database driver, and name the reason in the recipe column.
A service that already carries an SDK, an agent or its own OTLP client (`custom-otlp`)
gets neither a second one nor a second log bridge. When services export to an in-stack collector, the plan has one row for that
collector, wired as [export-contract.md](export-contract.md) § Protocol and temporality
says, and new rows route to it too. The routed services are "verification only"
rows with no files. In the closing table the collector's row carries the state of the
services it routes: `reporting` when they report, else `blocked` with their reason. A
service exporting `direct:` to another backend gets an env-only change (endpoint, headers,
protocol) and a note that the old backend stops receiving unless the user asks for dual
export (a collector). On Kubernetes,
annotation-based injection is the zero-code recipe only where an `Instrumentation`
resource the service can use **already exists** (the CRD alone proves nothing). `kubectl get instrumentations -A` reaches the
cluster, so it runs after approval: plan the in-image recipe's files, and a resource found
then goes into the deployment entry as `namespace/name`, the Dockerfile listed, unchanged. Creating
the `Instrumentation` or installing the Operator is a cluster change, never part of
this run.

## Logs are additive (Hard rule 4)

Bridge the logger the service already uses (appender, hook, transport); sink, format,
timestamps, timezone and levels stay byte-identical, or that service stays at level 2 and
you say so. Before bridging, read what it logs: request or response bodies, credentials,
tokens or personal data (names, emails, account identifiers) in the records keep it at
level 2 (so does a wrapper logger or dynamic fields you cannot read), even when the
developer chose 3; name the service and the reason, and interactive, ask before bridging
it. Three known traps, checked while wiring: .NET
`ClearProviders()` discards the provider the auto-instrumentation injects. Remove only
the providers you replace; winston (v3+) exports nothing until
`@opentelemetry/winston-transport` is installed, and the winston instrumentation then
injects the transport itself into loggers created after it loads (`--require` order), so
do not also attach `OpenTelemetryTransportV3` by hand; Go `otelhttp` (contrib v0.66+)
re-applies its span-name formatter after the handler returns, so give the route at wrap
time with `otelhttp.WithSpanNameFormatter` (or `otelhttp.WithRouteTag` per route) and set
`http.route` there, never inside the handler.

## Node recipe

`@opentelemetry/sdk-node` + `@opentelemetry/auto-instrumentations-node`, loaded with
`node --require ./otel.js`, versions resolved under Hard rule 9. Four things the zero-code
path leaves to you:

- **Construct no exporter, metric reader or log processor.** `new NodeSDK({ resource,
  instrumentations })` builds them from `OTEL_TRACES_EXPORTER=otlp`,
  `OTEL_METRICS_EXPORTER=otlp` and `OTEL_LOGS_EXPORTER=otlp` in the deployment entry.
  Constructor shapes drift: `sdk-logs` 0.222's
  `BatchLogRecordProcessor` takes `{ exporter }`.
- **An existing bootstrap that constructs exporters** keeps the `-proto` packages
  (`@opentelemetry/exporter-trace-otlp-proto`, `@opentelemetry/exporter-metrics-otlp-proto`,
  `@opentelemetry/exporter-logs-otlp-proto`); the `-otlp-http` siblings send JSON, ingest
  answers 415 (Hard rule 7), and Hard rule 9's guard fails the service.
- **`@opentelemetry/instrumentation-console` is not in `auto-instrumentations-node`** and
  lives on its own version line (0.4.x) with its own `npm view`
  lookup: a pin copied from a sibling (`^0.53.0`) fails `npm install`. Level 3 with `console.*` logging needs
  it; a winston or pino logger takes that logger's bridge instead (Hard rule 4).
- **Nest's built-in `Logger` writes through `process.stdout`**, not `console.*`, so
  `instrumentation-console` gets none of it. At level 3 bridge the winston or pino logger
  the app hands Nest (`app.useLogger()`, or the `logger` option of `NestFactory.create`);
  with only the built-in one, the service stays at level 2 and the plan says so (Hard rule 4).

## Read-only source (Inventory)

A compose entry that mounts the service's source tree read-only (`:ro`, or
`read_only: true` on the bind mount) is a plan-row fact: new
packages cannot be installed into that tree at start, so they go into the image — the row
names the Dockerfile (existing, or new: "needs a Dockerfile") among the files that change,
and the start command rebuilds.

## Build caches (Hard rule 9)

Build or run in a container when the host gates its toolchains, and mount a named volume
for the module or package cache so a repeated run never downloads twice (Go
`-v bluebox-gomod:/go/pkg/mod`, Node `-v bluebox-npm:/root/.npm`, Maven
`-v bluebox-m2:/root/.m2`, .NET `-v bluebox-nuget:/root/.nuget/packages`, Python
`-v bluebox-pip:/root/.cache/pip`); create it if missing, never remove it.

## Dependency source (wiring)

To read how a dependency behaves, ask its
toolchain where it lives; never search the disk for it (Hard rule 12). Go: the module path
from go.mod goes alone on the line after the command, where the shell never reads it:

```bash
/bin/sh -c 'IFS= read -r v; case $v in ""|*[!A-Za-z0-9._/~-]*) echo "not run";; *) go list -m -f "{{.Dir}}" -- "$v";; esac' <<'/'
<module>
/
```

It prints the module's directory in the module cache once `go get` or `go mod download`
fetched it, an empty line in a vendored module (the source is under `vendor/<module>`), and
`not run` for a value with a character outside `A-Za-z0-9._/~-`. Any package, an internal
one included, resolves the same way by its import path, with `go list -f "{{.Dir}}" -- "$v"`
in the `*)` branch; one known only by its short name, among the build's own dependencies,
with `go list -deps -f "{{.ImportPath}} {{.Dir}}" ./... | grep -F -- "$v"`. Node:
`node_modules/<package>/`. Python: the package's directory under the virtual environment's
`site-packages`.

## Rule 9 lookups (at install)

After consent, before anything is installed, read each candidate release's own
requirement, newest first, and pin the first that admits the version the repo declares:

| runtime | the repo declares | read per candidate |
|---|---|---|
| Go | the `go` line of `go.mod`, `go 1.24` read as `1.24.0` | `GoVersion` from `go list -m -json <module>@<version>` (several per call) for every module the `go get` will name, each on its own line (otel `v1.x`, its log modules `v0.x`, contrib `v0.x`), candidates from `go list -m -versions <module>` with pre-releases (`-rc.1`) skipped; then `go get <module>@<pin>`, never `@latest`, and `git diff go.mod` must leave the `go` line on the same release (`go get` may write `go 1.24` as `go 1.24.0`: leave it). If the release moved, `git checkout go.mod go.sum` and step down: editing the line back keeps the raised dependencies |
| Node | the base image tag, else the `engines.node` floor | `engines.node`, one line per version from `npm view '<package>@<range>' engines.node` |
| Python | the base image tag, else the `requires-python` floor | `requires-python`: `pip index versions <package> --python-version <X.Y>` lists only the releases that admit it, newest first (add `--pre` for the `0.NNbN` contrib packages, or it lists none) |
| Java, .NET | the target Java release or framework | the floor the release declares: its minimum Java (Maven), its target frameworks (NuGet) |

## A build already broken (Hard rule 9)

A build that fails without your change, in a file the plan did not name (a tsconfig's
`moduleResolution: node`, which TypeScript 7 no longer takes), is the repo's to fix:
never edit that file to go green. Ask before fixing it; unattended, or when the developer
keeps it, name it under Limitations and build-verify against it: the service is wired when
the build still compiles the files you changed and no error points at one. A build that
stops at that file compiles nothing: the service is `blocked` (`build_failed —` the error
it stopped on).

## Exporter guard (Hard rule 9)

Before recording the service, even on a green build, run its runtime's exporter guard;
a guard hit is `build_failed` until fixed. Node — the
manifest and the bootstrap file must carry no JSON exporter (Hard rule 7):
`grep -nE 'exporter-(trace|metrics|logs)-otlp-http([^a-z-]|$)' -- package.json '<bootstrap file>'`
(the file name comes from the repo: keep the single quotes and the `--`, and a name with
anything outside `A-Za-z0-9._/-` is not run — record `build_failed` without the name)
— exit 1 with nothing printed is the only pass; a line printed (exit 0), or exit 2
because a named file is missing, fails the service: remove the package, add the
`-proto` sibling, rebuild (or name the bootstrap file the plan row lists).
Not `npm ls --all`: it lists the JSON ones in every project. Python — the manifest must name the protobuf exporter, or
the `opentelemetry-exporter-otlp` umbrella that carries it:
`cat requirements*.txt pyproject.toml 2>/dev/null | grep -qE 'opentelemetry[-_]exporter[-_]otlp([-_]proto[-_]http)?([^a-z-]|$)'`
— a non-zero exit fails the service (`-proto-grpc` alone is not it).

## Exporter diagnostics per runtime

Workflow step 5's verification start carries the switch below ([verify.md](verify.md)).
Each row names
the level that does not print request headers (Hard rule 1); where that is unconfirmed
for the SDK the row stays at its default level and reads failure lines only. Check the
row against the installed SDK version first.

| language | first-start switch | what the log gives | grep |
|---|---|---|---|
| Node (`sdk-node`, exporters 0.2xx) | `OTEL_LOG_LEVEL=info`: export failures, no payload and no header (a rejected value's `Header "…" has invalid value` echo is dropped by the filter below). `debug` also logs the export body: do not set it | failures at info as `Export failed with non-retryable error: OTLPExporterError: <status text>` (`Unsupported Media Type`, `Unauthorized`, `Forbidden`, `Not Found` - the text, never the number), the metrics reader repeating it at error as `metrics export failed (…)`, a network error as `export request failure (error: …)`; success is silent and no attempt is logged, so a signal is wired only where the code registers its exporter, reader or bridge, or the env builds it | `-e 'export failed' -e 'export request'` plus a `{"stack":` line topped by an SDK or exporter frame |
| Java agent | none: the agent logs `Failed to export <signal>s. Server responded with HTTP status code N` at its default level; `-Dotel.javaagent.debug=true` is unconfirmed on headers: do not set it | failures per signal, with the number; success is silent, and every signal is wired unless its `OTEL_<SIGNAL>_EXPORTER` is `none` | `-e 'Failed to export'` |
| Python (`opentelemetry-instrument`) | none: the exporter's own logger reports failures at the default level; `OTEL_PYTHON_LOG_LEVEL=debug` makes `urllib3` print request headers: do not set it | `Failed to export … batch code: N` per signal; success is silent | `-e 'Failed to export' -e 'Transient error'` |
| .NET (auto-instrumentation) | `OTEL_DOTNET_AUTO_LOG_LEVEL` stays at its default `info` (`debug` is unconfirmed on headers) | the exporter's failures in the log file under `OTEL_DOTNET_AUTO_LOG_DIRECTORY` (`/var/log/opentelemetry/dotnet` by default), not on the container's stdout: read it with `<compose> exec '<service>' sh -c 'cat /var/log/opentelemetry/dotnet/*'` through the same greps and `sed`; success is silent | `-e 'Exporter failed' -e 'status code'` |
| Go | none: no env switch exists (`OTEL_LOG_LEVEL` is not read); the default error handler writes every failed export to stderr as `failed to send to <url>: 415 Unsupported Media Type` | failures per exporter; success is silent, and a signal is wired only where the code registers its provider | `-e 'failed to send'` |
