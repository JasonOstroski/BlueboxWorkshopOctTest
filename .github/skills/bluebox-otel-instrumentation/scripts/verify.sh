#!/usr/bin/env bash
# verify.sh — references/verify.md's two commands plus a hand-written question, guards built in.
#
#   bash <skill dir>/scripts/verify.sh logs --lang node|java|python|dotnet|go --service '<name>' \
#             (--compose "<compose>" | --logs-cmd '<command>') [--since 2m]
#       Reads the exporter's own log for the failure lines of that runtime, never the whole
#       log: greps the status lines, withholds a failure line that mentions a header (it is
#       counted, and a count means the transport is not confirmed), cuts query strings and
#       user-info out of URLs, masks a Dynatrace token and an Authorization, Api-Token,
#       Bearer, Basic or OTLP headers value wherever it stands, in the log and in the echoed
#       command alike (Hard rule 1). Runs the log command exactly once: a non-zero exit is a
#       run problem (wrong service name, container gone, no log file yet), never a clean
#       transport — exit 2, nothing shown. --compose is the compose
#       command the runtime probe found (`podman compose`, `docker compose`, ...);
#       --logs-cmd replaces the compose log command for a stack that is not compose
#       (`kubectl logs <pod>`, `journalctl -u <unit>`): one plain command, words grouped with double quotes.
#
#   bash <skill dir>/scripts/verify.sh ask [--env '<env>'] --window '<T1>..<now>' --services '<a>, <b>' \
#             --signals 'spans, logs, and metrics' [--settle '<seconds>'] [--print]
#       Runs the ONE batched check, verbatim from references/verify.md, scoped to the plan
#       table's environment name. Run from the repository root: with no --env it takes the
#       name .bluebox/instrumentation-run.json records (state-update.py --environment), and
#       an --env that differs from the recorded one is refused, both named: record the
#       developer's re-scope first. --settle 45 or 90 waits that long first, here, so the agent
#       never runs a sleep of its own, then ends the window at the ask. --print shows the
#       command instead of running it.
#
#   bash <skill dir>/scripts/verify.sh question [--print] <<'/'
#   [service=<name>]
#   [env=<env> | env=*]
#   <the question>
#   /
#       Asks one hand-written question. Every value comes from the quoted heredoc, so none
#       reaches a shell: service= and env= are checked like the ask's (an env= other than the
#       recorded one is refused), and the other lines, joined, go to bluebox as a single argument.
#       While the run record names an environment, a question carries env= or env=* (asked
#       across every environment, for host or cluster telemetry no environment name scopes).
#
# Exit: 0 read or ask done (the output is the evidence); 1 bad arguments; 2 the log command
# itself failed; 3 bluebox ended an ask or a question with no answer text, twice, whatever its exit
# (it is asked once more by itself): no evidence either way. Raise the tool's own timeout for the ask (Hard rule 11).
set -u
set -f
# strict-mode: off - it reads the log command's and bluebox's status (`rc=$?`); a grep with no hit is an answer
# zsh sets $0 to the function's name inside usage().
script=$0
# Bytes, not characters, here and in the children: a multibyte trail byte can be sh syntax, and BSD sed drops a line it cannot decode.
export LC_ALL=C

usage() {
  awk 'NR > 1 && !/^#/ { exit } NR > 1' <"$script" | sed 's/^# \{0,1\}//'
  exit 1
}
die() {
  printf 'verify.sh: %s\n' "$*" >&2
  exit 1
}

mode=${1:-}
[[ -n "$mode" ]] && shift
lang='' service='' compose='' logs_cmd='' since=2m env='' window='' services='' signals='' settle=- print=0
# bash fails a `shift 2` short of a value without shifting: a value flag given last would loop forever.
need_value() { [[ "$1" -gt 1 ]] || die "$2 needs a value"; }
while [[ $# -gt 0 ]]; do
  case $1 in
    --lang)
      need_value $# "$1"
      lang=$2
      shift 2
      ;;
    --service)
      need_value $# "$1"
      service=$2
      shift 2
      ;;
    --compose)
      need_value $# "$1"
      compose=$2
      shift 2
      ;;
    --logs-cmd)
      need_value $# "$1"
      logs_cmd=$2
      shift 2
      ;;
    --since)
      need_value $# "$1"
      since=$2
      shift 2
      ;;
    --env)
      need_value $# "$1"
      env=$2
      shift 2
      ;;
    --window)
      need_value $# "$1"
      window=$2
      shift 2
      ;;
    --services)
      need_value $# "$1"
      services=$2
      shift 2
      ;;
    --signals)
      need_value $# "$1"
      signals=$2
      shift 2
      ;;
    --settle)
      need_value $# "$1"
      settle=$2
      shift 2
      ;;
    --print)
      print=1
      shift
      ;;
    -h | --help) usage ;;
    *) die "unknown argument: $1" ;;
  esac
done

# Only the characters a service, environment or window can carry: anything else is not run.
safe() { case $2 in '' | *[!A-Za-z0-9._:+/@-]*) die "$1 must match [A-Za-z0-9._:+/@-]+ and not be empty" ;; esac }
# The environment name the run record carries (state-update.py writes it), or nothing when there is no
# record. Read as JSON, whatever its layout; a record that does not parse, or names a value --env could
# not take, stops the ask rather than letting another name through. A record or directory that is a
# link is not read: its name could come from outside the run.
recorded_env() {
  r=.bluebox/instrumentation-run.json
  [[ -d .bluebox ]] && [[ ! -L .bluebox ]] && [[ -f "$r" ]] && [[ ! -L "$r" ]] || return 0
  command -v python3 >/dev/null 2>&1 || die "$r exists but python3 is missing to read it; the hub's state-update.py needs it too"
  python3 -I -S -c 'import json, re, sys
try:
    with open(sys.argv[1], encoding="utf-8") as fh:
        doc = json.load(fh)
except (OSError, ValueError):
    sys.exit(3)
name = doc.get("environment", "") if isinstance(doc, dict) else ""
ok = isinstance(name, str) and re.fullmatch(r"[A-Za-z0-9._:+/@-]*", name)
sys.exit(4) if not ok else print(name)' "$r" \
    || die "$r does not parse as the run record, or its environment is not a name: the ask is not scoped to a guess"
}
# env is the run's name: the recorded one when none is given, and never one that differs from it.
scope_env() {
  rec=$(recorded_env) || exit 1
  if [[ -z "$env" ]]; then
    [[ -z "$rec" ]] || env=$rec
    return 0
  fi
  safe --env "$env"
  [[ -z "$rec" ]] || [[ "$env" = "$rec" ]] \
    || die "$1 '$env' is not the environment the run record names ('$rec'): ask in '$rec', or record the developer's re-scope first (state-update.py --environment '<name>' --decision ...)"
}
# Single-quote a value for a printed command, so a quote in a service name cannot become shell syntax.
shq() { printf "'%s'" "$(printf '%s' "$1" | sed "s/'/'\\\\''/g")"; }
# The one filter every log-derived line and the echoed log command pass through. It masks what
# state-update.py refuses, and its output passes that check again: a Dynatrace token, a query
# string, URL userinfo, an Authorization value, an Api-Token, Bearer or Basic value, an OTLP
# headers assignment; an Authorization value takes the rest of its line, a quoted headers value
# goes whole to its closing quote. The
# placeholder sits directly on the name so no separator survives.
mask() {
  sed -E -e 's/\?[^[:space:]]*//g' -e 's#://[^/[:space:]]*@#://#g' \
    -e 's/dt0[a-z][0-9]{2}\.[A-Za-z0-9._-]*/<token>/Ig' \
    -e 's/authorization[^[:alnum:]]*([=:]|api-token|bearer|basic).*/Authorization<token>/I' \
    -e 's/(api-token)[[:space:]:=]+[^[:space:]]+/\1<token>/Ig' \
    -e 's#(api-token|bearer|basic)[^[:alnum:]]*[A-Za-z0-9._~+/=-]{20,}#\1<token>#Ig' \
    -e "s/OTEL_EXPORTER_OTLP_HEADERS[[:space:]]*[=:][[:space:]]*(\"([^\"\\\\]|\\\\.)*\"?|'[^']*'?|[^[:space:]]*)/OTEL_EXPORTER_OTLP_HEADERS<token>/Ig"
}

# bluebox can end a turn with no answer text, on exit 0 or a failed turn: the same question once more, then say so.
# Backgrounded, its answer in a file, so a signal to this script ends the ask too.
run_ask() {
  command -v bluebox >/dev/null 2>&1 || die "bluebox is not on PATH"
  answer=$(mktemp) || die "no temporary file for the answer"
  pid=
  fin() {
    rm -f "$answer"
    exit "$1"
  }
  # shellcheck disable=SC2329 # invoked through the signal traps below
  stop() {
    [[ -z "$pid" ]] || {
      kill "$pid" 2>/dev/null
      wait "$pid" 2>/dev/null
    }
    fin "$1"
  }
  trap 'stop 129' HUP
  trap 'stop 130' INT
  trap 'stop 143' TERM
  for attempt in 1 2; do
    bluebox "$@" >"$answer" &
    pid=$!
    wait "$pid"
    rc=$?
    pid=
    out=$(cat "$answer")
    case $out in *[![:space:]]*)
      printf '%s\n' "$out"
      fin "$rc"
      ;;
    esac
    [[ "$attempt" = 2 ]] || printf 'verify.sh: bluebox ask ended with no answer text; asking once more\n' >&2
  done
  printf 'no answer: bluebox ask ended twice without answer text, which is evidence of nothing; a service left unverified is blocked (verify_unreadable)\n'
  fin 3
}

case $mode in
  logs)
    safe --service "$service"
    case $since in '' | *[!0-9smh]*) die "--since is a duration like 2m" ;; esac
    case $lang in
      # an SDK exception's top frame sits in an SDK, exporter or otlp-* package; an app error only passes through instrumentation frames
      node) greps="-e 'export failed' -e 'export request' -e '{\"stack\":\"[^\\]*\(\\\\[^n][^\\]*\)*\\\\n *at [^\\]*@opentelemetry/sdk-' -e '{\"stack\":\"[^\\]*\(\\\\[^n][^\\]*\)*\\\\n *at [^\\]*@opentelemetry/exporter-' -e '{\"stack\":\"[^\\]*\(\\\\[^n][^\\]*\)*\\\\n *at [^\\]*@opentelemetry/otlp-'" ;;
      java) greps="-e 'Failed to export'" ;;
      python) greps="-e 'Failed to export' -e 'Transient error'" ;;
      dotnet) greps="-e 'Exporter failed' -e 'status code'" ;;
      go) greps="-e 'failed to send'" ;;
      *) die "--lang is one of node, java, python, dotnet, go" ;;
    esac
    if [[ -n "$logs_cmd" ]]; then
      # Only words and quotes reach sh -c: no separator, pipe, redirect, substitution, glob, escape or newline, and never a blank command.
      case $logs_cmd in
        *[!A-Za-z0-9._:+/@=,\'\"\ -]*) die "--logs-cmd is one plain command, e.g. 'kubectl logs <pod>': letters, digits, spaces, quotes and ._:+/@=,- only" ;;
        *[!\ ]*) read_cmd=$logs_cmd ;;
        *) die "--logs-cmd is empty" ;;
      esac
    elif [[ -n "$compose" ]]; then
      case $compose in *[!A-Za-z0-9._\ /-]*) die "--compose is the probe's compose command, e.g. 'podman compose'" ;; esac
      if [[ "$lang" = dotnet ]]; then
        # .NET writes the exporter's failures to its log file, not to stdout (OTEL_DOTNET_AUTO_LOG_DIRECTORY).
        read_cmd="$compose exec $service sh -c 'cat /var/log/opentelemetry/dotnet/*'"
      else
        read_cmd="$compose logs --since $since $service"
      fi
    else
      die "logs needs --compose \"<compose>\" or --logs-cmd '<command>'"
    fi
    # An empty read is evidence only when the log command itself succeeded. One run: the raw
    # text stays in this variable and leaves it only through the filters below.
    raw=$(sh -c "$read_cmd" 2>&1)
    rc=$?
    if [[ "$rc" -ne 0 ]]; then
      printf 'log read failed (exit %s) for: %s\nfix the run (service name, container, log file), this is not a clean transport\n' "$rc" "$(printf '%s' "$read_cmd" | mask)"
      exit 2
    fi
    hits=$(printf '%s\n' "$raw" | eval "grep -ai $greps")
    # A failure line naming a header may carry its value: counted, never shown, never a clean read.
    held=$(printf '%s\n' "$hits" | grep -ciE 'authorization|header')
    out=$(printf '%s\n' "$hits" | grep -viE 'authorization|header' | mask)
    if [[ -n "$out" ]]; then
      printf '%s\n' "$out"
    fi
    if [[ "$held" -gt 0 ]]; then
      printf '%s failure line(s) for %s (%s) mention a header and are withheld: the transport is NOT confirmed; re-test the ingest header (Workflow step 4) before reading again\n' "$held" "$service" "$lang"
    elif [[ -z "$out" ]]; then
      printf 'no failure line for %s (%s) in the last %s: the transport is right for what the code exports\n' "$service" "$lang" "$since"
    fi
    ;;
  ask)
    scope_env --env
    [[ -n "$env" ]] || die "--env is the plan table's environment name; no run record names one here"
    safe --env "$env"
    [[ -n "$window" ]] || die "--window is the traffic window, <T1>..<now>"
    [[ -n "$services" ]] || die "--services lists the selected services"
    [[ -n "$signals" ]] || die "--signals names the signals the user selected, e.g. 'spans, logs, and metrics'"
    case $settle in - | 45 | 90) ;; *) die "--settle is 45 or 90 (seconds)" ;; esac
    if [[ "$print" != 1 ]] && [[ "$settle" != - ]]; then
      # Backgrounded, so a signal to this script ends the wait too.
      wait_pid=
      trap 'kill "$wait_pid" 2>/dev/null; exit 129' HUP
      trap 'kill "$wait_pid" 2>/dev/null; exit 130' INT
      trap 'kill "$wait_pid" 2>/dev/null; exit 143' TERM
      sleep "$settle" &
      wait_pid=$!
      wait "$wait_pid"
      trap - HUP INT TERM
      # Data exported during the settle belongs in the window, so it ends when the ask goes out.
      case $window in *..*) window="${window%..*}..$(date -u +%Y-%m-%dT%H:%M:%SZ)" ;; esac
    fi
    prompt="For the window $window: which of these services have $signals arriving — $services? Count by OTLP service.name, not by entity. For metrics: FIRST list every metric key that carries that service.name in the window (the catalog for that service - do not test guessed key names or prefixes), then judge from that list; any key the app exported counts - request, client-side (http.client.*), runtime, JVM - but list dt.* and other entity-derived keys separately and do not count them: dt.service.request.count/failure_count/response_time are derived from spans and exist for every service with inbound request spans. List per-service signals, the metric keys seen, and the values of vcs.repository.url.full on their spans."
    if [[ "$print" = 1 ]]; then
      [[ "$settle" = - ]] || printf 'sleep %s\n' "$settle"
      printf 'bluebox ask --env %s %s\n' "$(shq "$env")" "$(shq "$prompt")"
    else
      run_ask ask --env "$env" "$prompt"
    fi
    ;;
  question)
    # A value typed on the command line would reach the agent's shell before any check here.
    [[ -z "$env$service" ]] || die "question: service= and env= go in the heredoc, not on the command line"
    q=
    while IFS= read -r line || [[ -n "$line" ]]; do
      case $line in
        service=*) service=${line#service=} ;;
        env=*) env=${line#env=} ;;
        *) q="${q:+$q }$line" ;;
      esac
    done
    # The record is read whatever env= says: one that cannot be read stops env=* too.
    rec=$(recorded_env) || exit 1
    case $env in
      '*') env= ;;
      '')
        [[ -z "$rec" ]] || die "question: the run record names '$rec': put env=$rec in the heredoc, or env=* for telemetry no environment name scopes (host, cluster)"
        ;;
      *) scope_env env= ;;
    esac
    [[ -z "$service" ]] || safe --service "$service"
    [[ -n "$q" ]] || die "question: put the question in the quoted heredoc after the command"
    set -- ask
    [[ -z "$env" ]] || set -- "$@" --env "$env"
    [[ -z "$service" ]] || set -- "$@" --service "$service"
    if [[ "$print" = 1 ]]; then
      printf 'bluebox'
      for a in "$@" "$q"; do printf ' %s' "$(shq "$a")"; done
      printf '\n'
    else
      run_ask "$@" "$q"
    fi
    ;;
  *) usage ;;
esac
