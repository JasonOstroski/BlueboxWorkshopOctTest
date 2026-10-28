#!/bin/sh
# probe.sh - the skill's bounded, read-only probes (references/probes.md), one fixed command each:
#
#   /bin/sh <skill dir>/scripts/probe.sh runtime
#   /bin/sh <skill dir>/scripts/probe.sh telemetry <<'/'
#   <dir>
#   /
#   /bin/sh <skill dir>/scripts/probe.sh deploy
#   /bin/sh <skill dir>/scripts/probe.sh reach [--endpoint '<url>'] [--registry '<host>']
#
# Run from the repository root, each its own tool call with a 30 s timeout. Every probe ends its
# output with `probe-done`; a result without it did not finish. Nothing here writes anything.
#
# runtime: which of podman, docker and nerdctl is installed, its daemon state and its compose
#   command. It re-runs itself under an allowlisted environment and drops every PATH, HOME,
#   DOCKER_CONFIG and XDG_* directory that is relative or inside the checkout, as written or
#   resolved, so nothing the repository ships is executed. The filter is directory-scoped: a
#   symlink in a PATH directory outside the checkout still runs. A DOCKER_HOST, CONTAINER_HOST or
#   DOCKER_CONTEXT counts only as a local socket.
# telemetry: file:line of code reading OTEL_EXPORTER_OTLP_* or constructing an OTel provider, under
#   `export:` and `init:`, over the repository-relative directories read from stdin, one per line,
#   up to the lone `/`; a name outside A-Za-z0-9._/- or resolving outside the repository prints
#   `skipped:`. Only the system's grep, cut and sort run.
# deploy: names only, one line per deployed target under the repository root: `helm: <dir>` (a
#   Chart.yaml's directory, not a vendored subchart), `k8s: <file>` (a workload manifest outside
#   any chart), `serverless: <file>` (serverless.yml, or a SAM template.yaml); a name outside
#   A-Za-z0-9._/- is counted on `skipped:`, past 50 targets `truncated:`; test and example
#   directories are left out as in telemetry. Only the system's find, grep and sort run.
# reach: one HEAD, no header, to the registry and to the OTLP endpoint's /v1/traces: --endpoint,
#   else the shell's OTEL_EXPORTER_OTLP_ENDPOINT. --registry adds one registry host; each
#   target owns 10 s of the 30 s.
#
# Exit: 0 probed; 1 usage.

usage() {
  echo "usage: /bin/sh probe.sh runtime | telemetry <<'/' (dirs, then /) | deploy | reach [--endpoint <url>] [--registry <host>]" >&2
  exit 1
}

# Before the reset only `case` and `exec` run: an exported function can replace `[` or `test`, never these. The re-run
# marker is an argument, never an environment variable, so the environment cannot skip the reset.
case ${1-} in
runtime)
  case $# in 1) ;; *) usage;; esac
  exec /usr/bin/env -i "HOME=$HOME" "PATH=$PATH" "${DOCKER_HOST+DOCKER_HOST=}${DOCKER_HOST-_=}" "${DOCKER_CONTEXT+DOCKER_CONTEXT=}${DOCKER_CONTEXT-_=}" "${DOCKER_CONFIG+DOCKER_CONFIG=}${DOCKER_CONFIG-_=}" "${CONTAINER_HOST+CONTAINER_HOST=}${CONTAINER_HOST-_=}" "${XDG_CONFIG_HOME+XDG_CONFIG_HOME=}${XDG_CONFIG_HOME-_=}" "${XDG_RUNTIME_DIR+XDG_RUNTIME_DIR=}${XDG_RUNTIME_DIR-_=}" /bin/sh "$0" --runtime-reset
  ;;
--runtime-reset)
  set -f; unset -f podman docker nerdctl command cd pwd echo test; r=$(cd -P . && pwd); while test "$r" != / && test ! -e "$r/.git"; do r=${r%/*}; test -z "$r" && r=/; done; test -e "$r/.git" || r=$(cd -P . && pwd); o() { case $1 in /*) ;; *) return 1;; esac; y=$(cd -P "$1" 2>/dev/null && pwd) || y=$1; for x in "$1" "$y"; do while test -n "$x"; do test "$x" -ef "$r" && return 1; if test "$x" = /; then x=; else x=${x%/*}; test -z "$x" && x=/; fi; done; done; }; k() { test -z "$1" || o "$1"; }; p=; IFS=:; for d in $PATH; do o "$d" && p="$p${p:+:}$d"; done; unset IFS; PATH=${p:-/nonexistent}; o "$HOME" || HOME=/nonexistent; k "${DOCKER_CONFIG-}" || unset DOCKER_CONFIG; k "${XDG_CONFIG_HOME-}" || unset XDG_CONFIG_HOME; k "${XDG_RUNTIME_DIR-}" || unset XDG_RUNTIME_DIR; for rt in podman docker nerdctl; do b=$(command -v "$rt") || continue; case $b in /*) ;; *) continue;; esac; case $rt in docker) h=${DOCKER_HOST-}; test -z "$h" && test -n "${DOCKER_CONTEXT-}" && h=$("$b" context inspect 2>/dev/null --format "{{.Endpoints.docker.Host}}");; podman) h=${CONTAINER_HOST-};; *) h=;; esac; case $h in ""|unix://*|npipe://*) ;; tcp://*|ssh://*) echo "$rt: remote daemon ${h%%://*} - checked after consent"; continue;; *) echo "$rt: remote daemon other - checked after consent"; continue;; esac; c=none; "$b" compose version >/dev/null 2>&1 && c="$rt compose"; if test "$c" = none; then bc=$(command -v "$rt-compose") && case $bc in /*) "$bc" version >/dev/null 2>&1 && c="$rt-compose";; esac; fi; d=down; "$b" version --format "{{.Server.Version}}" >/dev/null 2>&1 && d=up; echo "$rt: daemon=$d compose=$c"; done; echo probe-done
  ;;
telemetry)
  case $# in 1) ;; *) usage;; esac
  unset -f command grep cut sort echo printf cd pwd test read; unset GREP_OPTIONS; LC_ALL=C; export LC_ALL; set -f; r=$(cd -P . && pwd -P); set --; while IFS= read -r d; do case $d in "") ;; *[!A-Za-z0-9._/-]*) echo "skipped: $d";; *) set -- "$@" "$d"; case $(cd -P "./$d" 2>/dev/null && pwd -P) in "$r"|"$r"/*) ;; *) echo "skipped: $d";; esac;; esac; done; for k in export init; do case $k in export) e="(Getenv|LookupEnv|getenv|GetEnvironmentVariable)\([[:punct:]]OTEL_EXPORTER_OTLP_|environ(\.get\(|\[)[[:punct:]]OTEL_EXPORTER_OTLP_|process\.env(\.|\[[[:punct:]])OTEL_EXPORTER_OTLP_|[[:punct:]]/v1/(traces|metrics|logs)[[:punct:]]";; init) e="(New|Set)(Tracer|Meter|Logger)Provider\(|(^|[^A-Za-z_.])(Tracer|Meter|Logger)Provider\(|NodeSDK\(|set_(tracer|meter|logger)_provider\(|configure_opentelemetry\(|OpenTelemetrySdk|AddOpenTelemetry\(|[A-Za-z_]*([Oo][Tt]el|[Tt]elemetry|[Tt]racing)[A-Za-z_]*\.((Init|Setup|Configure)[A-Za-z]*|Start)\(|(init|setup)(OTel|Otel|Telemetry|Tracing|Tracer)[A-Za-z]*\(|(init|setup|configure)_(otel|telemetry|tracing|tracer)[a-z_]*\(|Create(Tracer|Meter|Logger)ProviderBuilder\(|(Node|Basic)(Tracer|Meter|Logger)Provider\(|Sdk(Tracer|Meter|Logger)Provider\.builder\(";; esac; echo "$k:"; for u do (cd -P "./$u" 2>/dev/null && case $(pwd -P) in "$r"|"$r"/*) command -p grep -rnoIE --exclude="*_test.go" --exclude="*_test.py" --exclude="test_*.py" --exclude="conftest.py" --exclude="*.test.*" --exclude="*.spec.*" --exclude="*.md" --exclude="*.rst" --exclude="*.txt" --exclude="*.adoc" --exclude="*.sh" --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=vendor --exclude-dir=.venv --exclude-dir=venv --exclude-dir=env --exclude-dir=site-packages --exclude-dir=__pycache__ --exclude-dir=dist --exclude-dir=build --exclude-dir=target --exclude-dir=docs --exclude-dir=examples --exclude-dir=scripts --exclude-dir=test --exclude-dir=tests --exclude-dir=__tests__ --exclude-dir=testdata --exclude-dir=testutil -e "$e" -- . | while IFS= read -r l; do printf "%s\n" "$u/${l#./}"; done;; esac); done | command -p cut -d: -f1,2 | command -p sort -u; done; echo probe-done
  ;;
deploy)
  case $# in 1) ;; *) usage;; esac
  unset -f command find grep sort echo printf test read; unset GREP_OPTIONS; LC_ALL=C; export LC_ALL; set -f; q() { while IFS= read -r p; do printf "%s\n" "${p#./}"; done | command -p sort -u; }; { command -p find . \( -name .git -o -name node_modules -o -name vendor -o -name .venv -o -name venv -o -name .terraform -o -name dist -o -name build -o -name examples -o -name test -o -name tests -o -name testdata \) -prune -o -type f -name Chart.yaml -print | q | while IFS= read -r p; do d=${p%Chart.yaml}; d=${d%/}; case $d in "") d=.;; */charts/*) test -f "${d%/charts/*}/Chart.yaml" && d=;; charts/*) test -f Chart.yaml && d=;; esac; test -z "$d" || printf "helm %s\n" "$d"; done; command -p grep -rlIE --include="*.yaml" --include="*.yml" --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=vendor --exclude-dir=.venv --exclude-dir=venv --exclude-dir=.terraform --exclude-dir=dist --exclude-dir=build --exclude-dir=examples --exclude-dir=test --exclude-dir=tests --exclude-dir=testdata -e '^[[:space:]]*kind:[[:space:]]*(Deployment|StatefulSet|DaemonSet|CronJob|Job)[[:space:]]*$' -- . | q | while IFS= read -r p; do y=$p; c=; while test -z "$c" && test "$y" != .; do case $y in */*) y=${y%/*};; *) y=.;; esac; test -f "$y/Chart.yaml" && c=1; done; test -n "$c" || printf "k8s %s\n" "$p"; done; { command -p find . \( -name .git -o -name node_modules -o -name vendor -o -name .venv -o -name venv -o -name .terraform -o -name dist -o -name build -o -name examples -o -name test -o -name tests -o -name testdata \) -prune -o -type f \( -name serverless.yml -o -name serverless.yaml \) -path '*[!A-Za-z0-9._/-]*' -print; command -p find . \( -name .git -o -name node_modules -o -name vendor -o -name .venv -o -name venv -o -name .terraform -o -name dist -o -name build -o -name examples -o -name test -o -name tests -o -name testdata \) -prune -o -type f \( -name serverless.yml -o -name serverless.yaml \) ! -path '*[!A-Za-z0-9._/-]*' -print | while IFS= read -r p; do a=; b=; i=; while IFS= read -r l || test -n "$l"; do v=${l%%#*}; v=${v%"${v##*[![:space:]]}"}; case $v in "") ;; provider:*) w=${v#provider:}; w=${w#"${w%%[![:space:]]*}"}; b=; case $w in "") b=1; i=;; aws|\"aws\"|\'aws\') a=1;; esac;; [![:space:]]*) b=;; *) case $b in 1) test -n "$i" || i=${v%%[![:space:]]*}; case ${v#"$i"} in name:*) w=${v#"$i"name:}; w=${w#"${w%%[![:space:]]*}"}; case $w in aws|\"aws\"|\'aws\') a=1;; esac;; esac;; esac;; esac; done < "$p"; test -z "$a" || printf "%s\n" "$p"; done; command -p grep -rlIE --include=template.yaml --include=template.yml --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=vendor --exclude-dir=.venv --exclude-dir=venv --exclude-dir=.terraform --exclude-dir=dist --exclude-dir=build --exclude-dir=examples --exclude-dir=test --exclude-dir=tests --exclude-dir=testdata -e '^(Transform:|[[:space:]]+-)[[:space:]]*.?AWS::Serverless-' -- .; } | q | while IFS= read -r p; do printf "serverless %s\n" "$p"; done; } | { s=0; n=0; while IFS=' ' read -r k p; do case $p in *[!A-Za-z0-9._/-]*) s=$((s+1));; *) if test -e "$p"; then n=$((n+1)); test "$n" -gt 50 || printf "%s: %s\n" "$k" "$p"; else s=$((s+1)); fi;; esac; done; test "$s" -eq 0 || echo "skipped: $s"; test "$n" -le 50 || echo "truncated: $((n-50)) more"; }; echo probe-done
  ;;
reach)
  xe="" xr="" xo=""
  case $# in
    1) ;;
    3) case $2 in --endpoint) xe=$3;; --registry) xr=$3;; *) usage;; esac;;
    5) case $2,$4 in --endpoint,--registry) xe=$3 xr=$5;; --registry,--endpoint) xr=$3 xe=$5;; *) usage;; esac;;
    *) usage;;
  esac
  for v do case $v in "") usage;; esac; done
  case $xe in *[!A-Za-z0-9.:/_-]*) echo "otlp: not probed (a character outside A-Za-z0-9.:/_-)"; xo=skip;; esac
  case $xr in *[!A-Za-z0-9.:-]*|:*|*:*:*|*:|*:*[!0-9]*) echo "registry $xr: not probed (not a bare host name with an optional port)"; xr=;; esac
  command -v curl >/dev/null 2>&1 || { echo "curl: absent"; echo probe-done; exit 0; }; p() { c=$(curl -q -sI -o /dev/null -w "%{http_code}" --connect-timeout 5 --max-time 10 -- "$2"); case $c in 401|403|405|415) s=auth-gated;; 407|5??|000|"") s=unreachable;; [234]??) s=reachable;; *) s=unreachable;; esac; echo "$1: $s http=$c"; }; p registry https://registry-1.docker.io/v2/; test -z "$xr" || p "registry $xr" "https://$xr/v2/"; case $xo in skip) ;; *) ep=${xe:-${OTEL_EXPORTER_OTLP_ENDPOINT-}}; case $ep in http://*|https://*) a=${ep#*://}; case ${a%%[/?#]*} in *@*) echo "otlp: invalid";; *) p otlp "${ep%/}/v1/traces";; esac;; "") echo "otlp: unset";; *) echo "otlp: invalid";; esac;; esac; echo probe-done
  ;;
*) usage;;
esac
