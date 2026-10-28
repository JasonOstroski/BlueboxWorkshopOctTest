#!/bin/sh
# sh-only: runs on the user's machine, started as `/bin/sh` by the user's agent
# env-keys.sh — the names an env file sets, never a value (Hard rule 1).
#
#   /bin/sh <skill dir>/scripts/env-keys.sh <<'/'
#   <file>
#   /
#
# Prints one name per line for every `NAME=...` line of <file> (`export NAME=...`, indented
# or spaced around the `=` alike), and nothing from the right of a `=`. A value is read as a
# shell reads it, so a quote left open and a trailing backslash carry it onto the next lines,
# and those are skipped whole: a line of theirs that reads like `NAME=` is not shown. When
# lines were skipped that way a last line says how many, since a stray quote hides the names
# after it; `no names set` when there is none. This and the Header precondition's presence
# test are the only reads of an env file that may hold real values; a redaction written by
# hand prints the value on the machine where its pattern does not match.
#
# <file> comes from the repository, so it travels in a quoted heredoc the shell never reads:
# only the first line is taken, an argument is refused, and a path with anything outside
# A-Za-z0-9._/- is not opened. Shell builtins only: nothing here is looked up on PATH.
#
# Exit: 0 names printed; 1 called with an argument; 2 not a readable file; 3 `path not tested`.
set -eu

if [ $# -ne 0 ]; then
  printf '%s\n' "usage: /bin/sh env-keys.sh <<'/' with the file's path alone on the next line, then /" >&2
  exit 1
fi

f=
IFS= read -r f || :
case $f in
  "" | *[!A-Za-z0-9._/-]*)
    printf '%s\n' "path not tested"
    exit 3
    ;;
esac
# A regular file only: a FIFO or a device would hang or stream.
if [ ! -f "$f" ] || [ ! -r "$f" ]; then
  printf '%s\n' "not a readable file"
  exit 2
fi

cr=$(printf '\r')
open=
cont=0

# Walk one line's value text from the quote state the last line left; sets open (sq, dq or
# empty) and cont (1 when an unquoted backslash ends the line) for the next line.
scan() {
  s=$1
  cont=0
  while [ -n "$s" ]; do
    case $open in
      sq)
        case $s in
          *\'*)
            s=${s#*\'}
            open=
            ;;
          *) return ;;
        esac
        ;;
      dq)
        case $s in
          \"*)
            s=${s#?}
            open=
            ;;
          \\?*) s=${s#??} ;;
          \\) return ;;
          *)
            t=${s%%[\\\"]*}
            s=${s#"$t"}
            ;;
        esac
        ;;
      *)
        case $s in
          \'*)
            s=${s#?}
            open=sq
            ;;
          \"*)
            s=${s#?}
            open=dq
            ;;
          \\?*) s=${s#??} ;;
          \\)
            cont=1
            return
            ;;
          *)
            t=${s%%[\\\"\']*}
            s=${s#"$t"}
            ;;
        esac
        ;;
    esac
  done
}

lstrip() {
  while :; do
    case $1 in
      " "* | "	"*) set -- "${1#?}" ;;
      *) break ;;
    esac
  done
  stripped=$1
}

found=0
skipped=0
while IFS= read -r line || [ -n "$line" ]; do
  line=${line%"$cr"}
  if [ -n "$open" ] || [ "$cont" = 1 ]; then
    skipped=$((skipped + 1))
    scan "$line"
    continue
  fi
  lstrip "$line"
  line=$stripped
  case $line in
    "export "* | "export	"*)
      lstrip "${line#export}"
      line=$stripped
      ;;
  esac
  name=${line%%=*}
  [ "$name" != "$line" ] || continue
  while :; do
    case $name in
      *" " | *"	") name=${name%?} ;;
      *) break ;;
    esac
  done
  case $name in
    "" | [!A-Za-z_]* | *[!A-Za-z0-9_]*) continue ;;
  esac
  printf '%s\n' "$name"
  found=1
  scan "${line#*=}"
done <"$f"

[ "$found" = 1 ] || printf '%s\n' "no names set"
[ "$skipped" = 0 ] || printf '%s\n' "($skipped line(s) inside a quoted or continued value not shown)"
