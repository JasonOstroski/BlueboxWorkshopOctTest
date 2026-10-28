# Host/Prometheus/log/datastore collection

Follow only when the user wants Bluebox to ingest telemetry a service's own SDK doesn't emit (the receivers below). A **Collector deployment**
over the **same** OTLP endpoint and ingest token.

For Kubernetes cluster/node/pod telemetry, use [kubernetes.md](kubernetes.md).

## What this gives Bluebox

`hostmetrics` (the collector host's resources), `prometheus` (a service's existing
`/metrics` endpoint), `filelog` (log files) and datastore receivers (`postgresql`, `mysql`, `redis`, …).

## Boundaries and gates

- **App instrumentation is unchanged.**
- **Same Bluebox ingest contract.** Export over `http/protobuf` (`otlphttp`) to the Bluebox OTLP endpoint with the Bluebox ingest token from env/secret store, never inlined or
  committed; no separate credential, no extra scope.
- **Cumulative metric series need delta conversion.** Bluebox rejects them, so any pipeline with a cumulative source **must** include
  `cumulativetodelta`. `prometheus` and datastore receivers are mostly cumulative counters; `hostmetrics`
  is a **mix**: utilization gauges plus cumulative sums (`system.cpu.time`, `system.disk.io`, `system.network.io`).
- **Datastore credentials are privileged.** `postgresql`/`mysql`/`redis` receivers need a least-privilege monitoring
  user/password from secret/env, never inlined or committed.
- **Confirm the target.** Only configure a receiver for a signal the user asked for and a source that exists (a real `/metrics` endpoint,
  real log paths, a reachable datastore).

## Prerequisites

- A place to run the Collector: the monitored host/VM (for `hostmetrics`/`filelog`), a sidecar, or a standalone collector reaching
  the scrape/datastore targets.
- The **OpenTelemetry Collector Contrib** distribution (or any build with the `hostmetrics`, `prometheus`, `filelog`, and datastore receivers plus the
  `cumulativetodelta` processor). In a container, pin its image as `otel/opentelemetry-collector-contrib:<version>@sha256:<digest>`
  (on a host, that same release's binary, checked against its published checksums): after approval, resolve the newest release the way
  Hard rule 9 resolves package versions and take the image digest from the registry; never `latest`, never a digest from memory.

## Collector configuration

The example shows all four receivers; drop the ones the user did not ask for, pipeline entries included.

```yaml
extensions:
  health_check:
    endpoint: 0.0.0.0:13133

receivers:
  hostmetrics:
    collection_interval: 30s
    scrapers:
      cpu: {}
      memory: {}
      disk: {}
      filesystem: {}
      network: {}
      load: {}
  prometheus:
    config:
      scrape_configs:
        - job_name: app
          scrape_interval: 30s
          static_configs:
            - targets: ["127.0.0.1:9464"]         # the app's existing /metrics endpoint
  filelog:
    include: ["/var/log/app/*.log"]               # real log paths only
    include_file_path: true
    # add operators here only if you must parse structured fields; preserve event timestamps
    # IMPORTANT: before enabling, confirm the files (shipped verbatim) carry no credentials, tokens
    # or PII; if they may, drop that path and use SDK-side log export (Hard rule 4) instead.
  postgresql:
    endpoint: ${env:POSTGRES_ENDPOINT}            # host:port
    username: ${env:POSTGRES_MONITOR_USER}
    password: ${env:POSTGRES_MONITOR_PASSWORD}
    tls:
      insecure: false

processors:
  resourcedetection:
    detectors: [env, system]                      # adds host.name and OS attributes
  cumulativetodelta:
    max_staleness: 25h                            # keep above the collection/scrape interval

exporters:
  otlphttp/bluebox:
    endpoint: ${env:BLUEBOX_OTLP_ENDPOINT}                     # from `bluebox otlp-endpoint`
    headers:
      Authorization: ${env:BLUEBOX_OTLP_AUTH}                 # whole header value incl. scheme; from env/secret, never inlined

service:
  extensions: [health_check]
  pipelines:
    metrics:
      receivers: [hostmetrics, prometheus, postgresql]
      processors: [resourcedetection, cumulativetodelta]
      exporters: [otlphttp/bluebox]
    logs:
      receivers: [filelog]
      processors: [resourcedetection]
      exporters: [otlphttp/bluebox]
```

Set a stable `service.name`/host identity (`resourcedetection` plus `OTEL_RESOURCE_ATTRIBUTES` on the collector, or a `transform`
processor), never one that conflicts with an existing service identity.
Other datastore receivers (`mysql`, `redis`, …) follow `postgresql`.

## Required environment

**User's own terminal only.** The user provides the endpoint, auth header and any datastore credentials via env or a secret store:
hand the block over, never run it, never inline. `BLUEBOX_OTLP_AUTH` is the WHOLE `Authorization` value, scheme included, copied
from the Bluebox Setup page (Hard rule 8): `Bearer <token>` for a platform token (`dt0s16…`), `Api-Token <token>` for a classic one
(`dt0c01…`). The `POSTGRES_*` lines only when a datastore receiver is enabled:

```bash
export BLUEBOX_OTLP_ENDPOINT="<bluebox otlp-endpoint output>"
export BLUEBOX_OTLP_AUTH="<supplied by the user; keep out of tracked files>"
export POSTGRES_ENDPOINT="db-host:5432"
export POSTGRES_MONITOR_USER="<least-privilege monitoring user>"
export POSTGRES_MONITOR_PASSWORD="<from secret store>"
```

In Kubernetes, mount these from a `Secret` (as [kubernetes.md](kubernetes.md) does) rather than env literals.

## Verify

- Start the collector; confirm `health_check` is healthy and the collector isn't erroring on export (a `401/403`: the header isn't reaching the
  collector).
- Header check first, then the report: [export-contract.md](export-contract.md) § Protocol and temporality, on a collector.
- Ask Bluebox whether the new telemetry is arriving, e.g.:

```bash
bash <skill dir>/scripts/verify.sh question <<'/'
env=*
are host CPU/memory metrics arriving for host <host> in the last 15 minutes?
/
bluebox ask 'are metrics from the app /metrics scrape arriving in the last 15 minutes?'
```

- Missing metrics: check `cumulativetodelta` first.

## Report

Summarize: the receivers and why, their sources, `cumulativetodelta` on every metrics pipeline, credentials kept in env/secret,
uncommitted, and the verification state.
