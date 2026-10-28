# Kubernetes cluster monitoring

> **Scope: clusters without a Dynatrace Operator or ActiveGate.**

Follow only when the user asks Bluebox to monitor a **Kubernetes cluster** (cluster/node/pod metrics and Kubernetes events), not when instrumenting a
single service. Cluster-side, over the **same** OTLP endpoint and ingest token.

## What this gives Bluebox

Node, pod and cluster metrics, object state, and events as logs, carrying `k8s.*` resource attributes.

## Boundaries and gates

- **App instrumentation is unchanged.**
- **Cluster-scoped RBAC is privileged.** Needs a `ServiceAccount` + `ClusterRole` + `ClusterRoleBinding` with cluster-wide read on nodes, pods,
  events, workloads, and a `Role` + `RoleBinding` for its lease in `<ns>`. Get explicit user approval before applying it.
- **Same Bluebox ingest contract.** Hard rules 1, 7 and 8 apply unchanged; token lives in a Kubernetes `Secret` referenced by env.

## Prerequisites

- A running Kubernetes cluster and `kubectl` access with permission to create RBAC and workloads.
- The **OpenTelemetry Collector Contrib** distribution (or any build with the `k8s_cluster`, `kubelet_stats`, `k8s_events`, `otlp` receivers, the
  `k8sattributes`, `transform`, `filter`, `cumulativetodelta` processors, and `k8s_leader_elector`/`health_check` extensions).

## Topology

Deploy **one DaemonSet** of the Collector:

- every pod runs `kubelet_stats` for **its own node** (needs `K8S_NODE_NAME` = `spec.nodeName`);
- the `k8s_leader_elector` extension elects a **single** pod to run the cluster-scoped receivers (`k8s_cluster`, `k8s_events`).

## Secret (user supplies the auth header)

**User's own terminal only (bash or zsh).** Tell the user to create the Secret there; never run the block below yourself, and never offer it through this
shell or the agent's `!` prefix: the value would land in the transcript (Hard rule 1). The user copies the whole `Authorization` value, scheme included - `Bearer <token>` or `Api-Token <token>`: what follows `Authorization=` inside the quotes of the line the Setup page's Copy token gives, without the `Authorization=` key itself, which the collector config adds (Hard rule 8).

**Avoid `--from-literal` and `echo '<value>'` with a real credential.** The block asks for it at a hidden prompt, so it reaches
neither history nor process arguments, and passes it through a fresh mode-600 `mktemp` file its exit trap deletes, also when `kubectl` fails or the user interrupts. It is one subshell with no
comment lines, so a paste runs whole in bash and in interactive zsh (which reads `#` as a command) and the value never stays in
the user's shell. Fill `<ns>` only with a DNS label (lowercase letters, digits and `-`, at most 63 characters); anything else, ask.
`<ns>` is a namespace of the collector's own, never `kube-system` or one other workloads share: the lease Role below may write any
Lease in it.

```bash
(
  f=; trap 'rm -f -- "$f"' EXIT; trap 'exit 130' INT TERM HUP
  printf 'Authorization value: '; read -rs BLUEBOX_OTLP_AUTH; echo
  f="$(mktemp)" && printf '%s' "$BLUEBOX_OTLP_AUTH" > "$f"
  kubectl create secret generic bluebox-otlp \
    --namespace '<ns>' \
    --from-file=otlp-auth="$f"
)
```

**An app workload's chart or manifest:** the user runs the same block with `<ns>` the workload's
namespace (no RBAC here), and its container reads the Secret, never a value in the file:

```yaml
env:
  - name: BLUEBOX_OTLP_AUTH
    valueFrom: { secretKeyRef: { name: bluebox-otlp, key: otlp-auth } }
  - name: OTEL_EXPORTER_OTLP_HEADERS
    value: "Authorization=$(BLUEBOX_OTLP_AUTH)"
```

## RBAC (privileged, get approval)

```yaml
apiVersion: v1
kind: ServiceAccount
metadata: { name: otelcol-bluebox, namespace: <ns>, labels: { app: otelcol-bluebox } }
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata: { name: otelcol-bluebox, labels: { app: otelcol-bluebox } }
rules:
  - apiGroups: [""]
    resources: [events, namespaces, namespaces/status, nodes, nodes/spec, nodes/stats,
                persistentvolumes, persistentvolumeclaims, pods, pods/status,
                replicationcontrollers, replicationcontrollers/status, resourcequotas, services]
    verbs: [get, list, watch]
  - apiGroups: [apps]
    resources: [daemonsets, deployments, replicasets, statefulsets]
    verbs: [get, list, watch]
  - apiGroups: [batch]
    resources: [jobs, cronjobs]
    verbs: [get, list, watch]
  - apiGroups: [autoscaling]
    resources: [horizontalpodautoscalers]
    verbs: [get, list, watch]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata: { name: otelcol-bluebox, labels: { app: otelcol-bluebox } }
roleRef: { apiGroup: rbac.authorization.k8s.io, kind: ClusterRole, name: otelcol-bluebox }
subjects:
  - { kind: ServiceAccount, name: otelcol-bluebox, namespace: <ns> }
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata: { name: otelcol-bluebox-lease, namespace: <ns>, labels: { app: otelcol-bluebox } }
rules:
  - apiGroups: [coordination.k8s.io]
    resources: [leases]
    verbs: [get, list, watch, create, update, patch, delete]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata: { name: otelcol-bluebox-lease, namespace: <ns>, labels: { app: otelcol-bluebox } }
roleRef: { apiGroup: rbac.authorization.k8s.io, kind: Role, name: otelcol-bluebox-lease }
subjects:
  - { kind: ServiceAccount, name: otelcol-bluebox, namespace: <ns> }
```

The ClusterRole is cluster-wide read only. The leader elector's `leases` writes sit in a Role in `<ns>`, where its
`lease_namespace` (`POD_NAMESPACE`) points.

## Collector configuration

```yaml
extensions:
  health_check:
    endpoint: 0.0.0.0:13133
  k8s_leader_elector:
    auth_type: serviceAccount
    lease_name: bluebox-k8smonitoring
    lease_namespace: ${env:POD_NAMESPACE}

receivers:
  k8s_events:
    auth_type: serviceAccount
    k8s_leader_elector: k8s_leader_elector
  kubeletstats:
    auth_type: serviceAccount
    collection_interval: 10s
    node: ${env:K8S_NODE_NAME}
    metric_groups: [node, pod, container, volume]
  k8s_cluster:
    auth_type: serviceAccount
    collection_interval: 10s
    k8s_leader_elector: k8s_leader_elector

processors:
  cumulativetodelta:
    max_staleness: 25h                    # keep above the collection/scrape interval
  filter:
    error_mode: ignore
  k8sattributes:
    extract:
      metadata: [k8s.pod.name, k8s.pod.uid, k8s.namespace.name, k8s.node.name,
                 k8s.deployment.name, k8s.replicaset.name, k8s.statefulset.name,
                 k8s.daemonset.name, k8s.job.name, k8s.cronjob.name, k8s.container.name, k8s.cluster.uid]
    pod_association:                    # scraped data has no client connection; match on resource attributes
      - sources: [{from: resource_attribute, name: k8s.pod.uid}]
      - sources: [{from: resource_attribute, name: k8s.pod.name},
                  {from: resource_attribute, name: k8s.namespace.name}]
  transform:
    error_mode: ignore
    metric_statements: &k8s_workload
      - context: resource
        statements:
          - set(attributes["k8s.cluster.name"], "${env:CLUSTER_NAME}")
    log_statements: *k8s_workload

exporters:
  otlphttp/bluebox:
    endpoint: ${env:BLUEBOX_OTLP_ENDPOINT}                       # from `bluebox otlp-endpoint`
    headers:
      Authorization: ${env:BLUEBOX_OTLP_AUTH}                    # whole header value incl. scheme; from the Secret, never inlined

service:
  extensions: [health_check, k8s_leader_elector]
  pipelines:
    metrics/node:
      receivers: [kubeletstats]
      processors: [filter, k8sattributes, transform, cumulativetodelta]
      exporters: [otlphttp/bluebox]
    metrics/cluster:
      receivers: [k8s_cluster]
      processors: [k8sattributes, transform, cumulativetodelta]
      exporters: [otlphttp/bluebox]
    logs/events:
      receivers: [k8s_events]
      processors: [transform]
      exporters: [otlphttp/bluebox]
```

Notes:

- Scrapes **cluster/node/pod telemetry only**, with **no `otlp` receiver and no `traces` pipeline**: app services keep exporting their own
  traces/metrics/logs **directly** to Bluebox. Do not add an in-cluster OTLP gateway here to instrument apps.
- `k8s_events` is maturing: cluster events are best-effort; never block the metrics pipelines on them.

## Required environment (Downward API + config)

Inject on the DaemonSet pod spec:

```yaml
env:
  - name: K8S_NODE_NAME
    valueFrom: { fieldRef: { fieldPath: spec.nodeName } }
  - name: POD_NAMESPACE
    valueFrom: { fieldRef: { fieldPath: metadata.namespace } }
  - name: CLUSTER_NAME
    value: "<a stable name for this cluster>"
  - name: BLUEBOX_OTLP_ENDPOINT
    value: "<bluebox otlp-endpoint output>"
  # Whole Authorization value, scheme included, as the Setup page renders it (Hard rule 8):
  # "Bearer <token>" for a platform token (dt0s16…), "Api-Token <token>" for a classic one (dt0c01…).
  - name: BLUEBOX_OTLP_AUTH
    valueFrom: { secretKeyRef: { name: bluebox-otlp, key: otlp-auth } }
```

Run the DaemonSet in `<ns>`, where its Secret and ServiceAccount are, with `serviceAccountName: otelcol-bluebox` and its image as `otel/opentelemetry-collector-contrib:<version>@sha256:<digest>`:
after approval, resolve the newest release the way Hard rule 9 resolves package versions and take its digest from the registry; never
`latest`, never a digest from memory.

## Verify

- Apply RBAC (after approval), Secret, config, and the DaemonSet; confirm pods are `Running` and the `health_check` extension is healthy.
- Confirm the collector isn't erroring on export. A `401/403` means the value isn't reaching the collector or carries the wrong
  scheme: have the user re-copy it whole from the Setup page.
- Header check first, then the report: [export-contract.md](export-contract.md) § Protocol and temporality, on a collector.
- Ask Bluebox whether cluster telemetry is arriving, e.g.:

```bash
bash <skill dir>/scripts/verify.sh question <<'/'
env=*
are Kubernetes cluster or pod metrics and events arriving for cluster <CLUSTER_NAME> in the last 15 minutes?
/
```

## Declared criticality (Bluebox critical-components ranking)

Bluebox ranks a service by the `primary_tags.criticality` span resource attribute (`high`/`medium`/`low`); without it, on derived fragility alone.

**How to set it (the only supported path with direct export):** in the service's environment,

```bash
OTEL_RESOURCE_ATTRIBUTES="primary_tags.criticality=high"
```

Bluebox reads it from the first matching **app span**. App services export directly, not through the cluster collector, so its
`k8sattributes` processor can't set it.

## Report

Summarize: the cluster, its RBAC applied with the user's approval, the signals, the ingest token kept in an uncommitted
Kubernetes Secret, and the verification state.
