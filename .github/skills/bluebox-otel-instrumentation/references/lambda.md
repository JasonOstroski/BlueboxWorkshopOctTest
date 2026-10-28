# AWS Lambda instrumentation

Follow only when the user asks Bluebox to instrument an **AWS Lambda function**, not a long-running service.

## Why Lambda is different

- **The runtime freezes between invocations**, right after the handler returns, so a `BatchSpanProcessor` that flushes on a timer or on process
  exit loses buffered spans.
- **Cold starts matter.** Instrumentation must be ready before the first invocation; export must not add unbounded response latency.

## Path A (recommended): AWS-managed OpenTelemetry Lambda layer

Add the layer for the function's runtime (`opentelemetry-lambda` / ADOT): auto-instrumentation **and** an in-process Collector extension,
flushing on `runtimeDone`.

Wiring:

- Attach the correct layer ARN for the function's runtime/region, looked up after approval (the current one from its publisher's docs,
  never a stale hardcoded ARN), and check its publisher, the ARN's account field: `184161586896` (`open-telemetry/opentelemetry-lambda`)
  or `901920570463` (ADOT). For any other account, ask before attaching it.
- Set the handler wrapper the layer documents (for example `AWS_LAMBDA_EXEC_WRAPPER=/opt/otel-instrument` for Node.js/Python).
- The SDK exports to the extension (`http://localhost:4318`). Give it a Collector config exporting to the Bluebox OTLP endpoint, shipped in
  the function package and named by `OPENTELEMETRY_COLLECTOR_CONFIG_URI` (newer layers) or `OPENTELEMETRY_COLLECTOR_CONFIG_FILE` (older
  layers): a local path such as `/var/task/collector.yaml`, never a remote URI.

Minimal extension config:

```yaml
receivers:
  otlp:
    protocols:
      http:
      grpc:
processors:
  batch:
exporters:
  otlphttp:
    endpoint: ${env:BLUEBOX_OTLP_ENDPOINT}
    headers:
      Authorization: ${env:BLUEBOX_OTLP_AUTH}   # whole header value incl. scheme, from a secret-backed env var
service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [otlphttp]
```

## Path B: SDK exports directly to Bluebox (no bundled Collector)

Point the SDK exporter at Bluebox and make export freeze-safe:

- Set `OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf`, `OTEL_EXPORTER_OTLP_ENDPOINT=<Bluebox OTLP endpoint>`, and
  `OTEL_EXPORTER_OTLP_HEADERS="Authorization=<value from the Bluebox Setup page>"` (secret-backed, never inlined; the scheme comes in that value,
  never composed).
- Node.js: depend on `@opentelemetry/exporter-trace-otlp-proto` (and `-metrics-`/`-logs-` siblings), or let `@opentelemetry/sdk-node` pick an exporter
  from `OTEL_EXPORTER_OTLP_PROTOCOL`. A self-constructed `*-otlp-http` exporter sends JSON, which ingest rejects with **415** (Hard rule 7).
- Do **not** rely on `BatchSpanProcessor` flush-on-exit. Call `forceFlush()` on the tracer/span processor before the handler returns, or use a
  Lambda-aware wrapper that flushes on `runtimeDone`.
- Keep the exporter timeout well under the function timeout.

Path B is for functions with their own SDK bootstrap or that can't add a layer.

## Bluebox export contract (same as the main skill)

- Hard rules 1, 7 and 8 apply unchanged: `http/protobuf` to the Bluebox OTLP endpoint, delta temporality for metrics, the `Authorization` value whole
  as the Setup page shows it, held in a secret-backed Lambda environment variable, never committed.

## Resource attributes for Lambda

Set:

- `service.name` - the logical service (via `OTEL_SERVICE_NAME`).
- `cloud.provider=aws`
- `cloud.platform=aws_lambda`
- `cloud.resource_id=<function ARN>` - the full `arn:aws:lambda:<region>:<account>:function:<name>`.
- `faas.name=<function name>` and `faas.version=<version or alias>`.

The layer sets several; add missing ones via `OTEL_RESOURCE_ATTRIBUTES`, never overwriting a correct auto-detected value with a guess.

## Verify

The header lives in the function's configuration, where you cannot test it: before the invocation, ask whether it is set and take
the answer, as Workflow step 4 does for a variable in the user's terminal. No header is `blocked` (`no_token`), nothing invoked.

Invoke the function at least once, note the wall-clock time and `OTEL_SERVICE_NAME`, then verify through Bluebox:

```bash
bash <skill dir>/scripts/verify.sh question <<'/'
service=<OTEL_SERVICE_NAME>
env=<env>
are spans arriving for <function> around <recorded-test-time>?
/
```

A name the script refuses (exit 1) leaves the function `blocked` (`other: name refused by verify.sh`).

Report per the closing summary's three states: no token (`no_token`), no workspace (`no_endpoint`) or no invocation
(`not_started`) is `blocked`; no answer from `bluebox ask` is `blocked` (`verify_unreadable`); never verified.

## Boundaries

- Does not set up managed-service monitoring, provider Lambda platform metrics, RUM, AppSec, or dashboards/alerts: only
  the function's own traces (optionally metrics and logs).
