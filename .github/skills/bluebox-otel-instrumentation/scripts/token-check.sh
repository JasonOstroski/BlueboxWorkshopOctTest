#!/bin/sh
# sh-only: runs on the user's machine, started as `/bin/sh` by the user's agent
# token-check.sh — one empty OTLP export per signal with the user's ingest header; prints the status codes, never the token (Hard rule 1).
#
#   /bin/sh <skill dir>/scripts/token-check.sh <<'/'
#   <source>
#   <endpoint>
#   /
#
# <source> is where the header lives: an env file's path (its last OTEL_EXPORTER_OTLP_HEADERS=
# line, quotes and `export` dropped), `-` for OTEL_EXPORTER_OTLP_HEADERS in this shell, or
# `~/.bluebox/ingest-token.env` for the token-file convention (scheme from the prefix: dt0s16
# Bearer, dt0c01 Api-Token). <endpoint> is the OTLP base URL, https unless the host is loopback;
# `/v1/<signal>` is appended for traces, metrics and logs, each an empty export request, so
# nothing is ingested. The header reaches curl on its stdin, never its argv. Prints one line,
# `ingest-token: <verdict> traces=<code> metrics=<code> logs=<code>`:
#   accepted   every signal 2xx, or a 400/415 that judged the body after the token passed;
#   rejected   any 401 or 403, then `missing: <scope>` per scope a response body names;
#   unchecked  otherwise (000 = no answer): this check proves nothing either way;
#   absent     no Authorization value at <source>; nothing sent.
# Both lines come from a quoted heredoc the shell never reads; anything outside
# A-Za-z0-9._/- in <source>, or a URL with user-info or whitespace, is refused.
#
# Exit: 0 checked or absent; 1 usage or a refused line; 2 <source> not a readable file.
set -eu
set -f
export LC_ALL=C

if [ $# -ne 0 ]; then
  printf '%s\n' "usage: /bin/sh token-check.sh <<'/' with <source> and <endpoint> on the next two lines, then /" >&2
  exit 1
fi
src='' ep=''
IFS= read -r src || :
IFS= read -r ep || :
case $src in
  "" | *[!A-Za-z0-9._/~-]*)
    printf '%s\n' "source not tested" >&2
    exit 1
    ;;
esac
case $ep in
  https://* | http://127.0.0.1[:/]* | http://127.0.0.1 | http://localhost[:/]* | http://localhost | "http://[::1]" | "http://[::1]:"* | "http://[::1]/"*) ;;
  *)
    printf '%s\n' "endpoint not https or loopback" >&2
    exit 1
    ;;
esac
a=${ep#*://}
case ${a%%[/?#]*} in
  "" | *@*)
    printf '%s\n' "endpoint refused" >&2
    exit 1
    ;;
esac
case $ep in
  *[[:space:]]* | *\"* | *\'* | *\\*)
    printf '%s\n' "endpoint refused" >&2
    exit 1
    ;;
esac
command -v curl >/dev/null 2>&1 || {
  printf '%s\n' "ingest-token: unchecked traces=000 metrics=000 logs=000 (curl absent)"
  exit 0
}

# The Authorization value, scheme included, or empty.
v=
case $src in
  -)
    v=${OTEL_EXPORTER_OTLP_HEADERS:-}
    ;;
  \~/.bluebox/ingest-token.env)
    f=$HOME/.bluebox/ingest-token.env
    if [ ! -f "$f" ] || [ ! -r "$f" ]; then
      printf '%s\n' "not a readable file"
      exit 2
    fi
    t=$(sed -n 's/^BLUEBOX_INGEST_TOKEN=\([A-Za-z0-9._-]*\)[[:blank:]]*$/\1/p' "$f" | tail -n 1)
    case $t in
      dt0s16.?*) v="Authorization=Bearer $t" ;;
      dt0c01.?*) v="Authorization=Api-Token $t" ;;
    esac
    ;;
  *~*)
    printf '%s\n' "source not tested" >&2
    exit 1
    ;;
  *)
    if [ ! -f "$src" ] || [ ! -r "$src" ]; then
      printf '%s\n' "not a readable file"
      exit 2
    fi
    v=$(sed -n 's/^[[:space:]]*\(export[[:space:]][[:space:]]*\)\{0,1\}OTEL_EXPORTER_OTLP_HEADERS=//p' "$src" | tail -n 1 | tr -d '\r' | sed 's/[[:blank:]]*$//')
    case $v in
      \"*\") v=${v#\"} v=${v%\"} ;;
      \'*\') v=${v#\'} v=${v%\'} ;;
    esac
    ;;
esac
# OTLP headers are comma-separated key=value pairs; Authorization may sit anywhere among them.
case ,$v in
  *,Authorization=*)
    v=${v#*Authorization=}
    v=${v%%,*}
    ;;
  *) v= ;;
esac
case $v in
  "Bearer "?* | "Api-Token "?*) ;;
  *)
    printf '%s\n' "ingest-token: absent"
    exit 0
    ;;
esac

# Each body stays in memory and only the scope names are kept: a body may echo the header back.
scopes='openpipeline:(traces|metrics|logs):ingest|openTelemetryTrace\.ingest|metrics\.ingest|logs\.ingest|storage:(logs|metrics|events|spans):write'
verdict=accepted line='' missing=''
for sig in traces metrics logs; do
  # `|| :`: curl exits non-zero when nothing answers; the -w code is then 000, which is the `unchecked` verdict, not a failure of this script.
  out=$(printf 'Authorization: %s\n' "$v" | curl -q -s -X POST -H @- -H "Content-Type: application/x-protobuf" --data-binary "" \
    -w "\n%{http_code}" --connect-timeout 5 --max-time 10 --max-filesize 65536 -- "${ep%/}/v1/$sig" || :)
  code=${out##*
}
  case $code in [0-9][0-9][0-9]) ;; *) code=000 ;; esac
  line="$line $sig=$code"
  case $code in
    2?? | 400 | 415) ;;
    401 | 403)
      verdict=rejected
      # `|| :`: grep exits 1 when the body names no scope; the verdict is already rejected.
      missing="$missing
$(printf '%s\n' "${out%
*}" | grep -oE "$scopes" || :)"
      ;;
    *) [ "$verdict" = rejected ] || verdict=unchecked ;;
  esac
done
printf '%s\n' "ingest-token: $verdict$line"
if [ "$verdict" = rejected ]; then
  printf '%s\n' "$missing" | sed '/^$/d' | sort -u | sed 's/^/missing: /'
fi
exit 0
