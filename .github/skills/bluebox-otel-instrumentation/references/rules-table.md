# Rules for this stack

**Rules for this stack** closes the plan in the shape the hub's plan step gives; a rule
that does not bind the chosen recipe gets no row. Candidate rows: 3 (the
zero-code package chosen, or why an SDK); 4, level 3 only (the logger bridged, by name);
7 (the `OTEL_*_EXPORTER` selectors, or the exporter packages a bootstrap constructs, the protobuf ones: Node's `*-otlp-proto` and never its
`*-otlp-http` (JSON), Python's `opentelemetry-exporter-otlp-proto-http`, and the two env
vars); 8 (the one location the `Authorization` value goes into, the one the handover
names too, and the quoting its consumer needs - quoted in a sourced `.env`, either quote in a compose `env_file`, unquoted in a
Docker `--env-file`; the value never read); 9 (the declared version; each pin is resolved
at install, against the declared runtime); and an `SDK` row naming the classes of the metric reader
(level 2 and up) and log processor (level 3) a bootstrap constructs. Services on one
recipe share a row; a row that differs by service names it. A Go plan at level 1 in a
compose stack has four rows (values illustrative):

| rule | binds here | resolved value |
|---|---|---|
| 3 | no zero-code for Go; SDK, the registry covers `net/http` and `database/sql` | `go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp`, `github.com/XSAM/otelsql`; exporters left to `go.opentelemetry.io/contrib/exporters/autoexport` |
| 7 | `autoexport` takes the protocol from env, no exporter constructed | `OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf`, `OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE=delta` |
| 8 | compose `env_file: .env` | `OTEL_EXPORTER_OTLP_HEADERS` in `.env`, quoted or not; value never read |
| 9 | `go 1.22` in `go.mod`; newest release whose `GoVersion` is at most `1.22.0` | `…/otelhttp`, `…/autoexport`, `github.com/XSAM/otelsql`: resolved at install, against the declared runtime |

A Node SDK plan at level 3 has five (values illustrative):

| rule | binds here | resolved value |
|---|---|---|
| 3 | SDK: an in-house RPC layer nothing in the registry covers; bootstrap `src/otel.js` | `@opentelemetry/sdk-node` + `@opentelemetry/auto-instrumentations-node` for HTTP and pg |
| 4 | winston 3 in `src/logger.js`; the instrumentation injects the transport | `@opentelemetry/winston-transport`; no `OpenTelemetryTransportV3` by hand |
| 7 | `NodeSDK` builds every exporter from env | `OTEL_TRACES_EXPORTER=otlp`, `OTEL_METRICS_EXPORTER=otlp`, `OTEL_LOGS_EXPORTER=otlp`; no exporter package and no `*-otlp-http` in `package.json`; `OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf`, `OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE=delta` |
| 8 | `.env` sourced by `npm start` | `OTEL_EXPORTER_OTLP_HEADERS` in `.env`, quoted (the shell strips the quotes); value never read |
| 9 | `engines.node >=18.19` in `package.json`; newest line whose `engines.node` admits it | `@opentelemetry/sdk-node`, `@opentelemetry/auto-instrumentations-node`, `@opentelemetry/winston-transport`: resolved at install, against the declared runtime |

**Placement.** Its own table, never folded into the plan table or the question; the hub's
order rule places it.

## Plan rows

Files a row names: the Dockerfile or start command, the deployment entry; for SDK recipes the
bootstrap and the request-handling files (`handlers*`, `routes*`, `controllers*`, the mux
registration; one left untouched is reported "listed, unchanged"); for level 3 the logging
configuration; for a read-only source mount the Dockerfile ([language-traps.md](language-traps.md)
§ Read-only source).
