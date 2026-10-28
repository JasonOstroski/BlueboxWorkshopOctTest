#!/usr/bin/env python3
"""Update the run record in .bluebox/, atomically, and render its readable copy.

The record write is part of the run (references/state-resume.md): one call per service, the
moment its build-verify passes or it is marked blocked/skipped, and one per step report and
per answer. Every call replaces .bluebox/instrumentation-run.json and renders
.bluebox/instrumentation-run.md from it. Each file is replaced, never written over, so an
interruption leaves the old one or the new one, never a half-written one.

Usage (every value in single quotes, a ' inside one written '\\''; names, paths and details come from the repository):
  python3 <skill dir>/scripts/state-update.py --name 'pricing-service' --status wired \
      --file 'src/pricing-service/main.go' --file 'src/pricing-service/Dockerfile' \
      --detail 'zero-code Go SDK, logs bridged'
  python3 <skill dir>/scripts/state-update.py --name 'cart' --status blocked --reason build_failed \
      --detail 'dotnet restore NU1101 for OpenTelemetry.AutoInstrumentation'
  python3 <skill dir>/scripts/state-update.py --step plan --environment '<env>' --decision plan '<question>' '<answer>' developer <<'BLUEBOX_RECORD_END'
  > <the step's report as printed, every line opening with "> ", a blank one ">">
  BLUEBOX_RECORD_END
  The same call per step, the moment it ends: --step scan and --step plan right after the answer,
  --step instrument after the last service entry, --step verify once the ask is judged,
  --step handover with the closing summary. A report never passed leaves its section _pending_, or
  _not run_ once the handover is recorded.
  --environment records the plan table's environment name once; scripts/verify.sh ask reads it from
  the record. Changing a recorded name is a re-scope: it needs a --decision by developer in the same call.
  --deploy-target 'helm: deploy/chart', once per line of probe.sh deploy, goes with --step scan;
  --verified-scope local|deployed, what the verification reached, with --step verify.

No secrets in the record, ever (Hard rule 1): name a header, never reproduce it. The check
is a tripwire for the shapes the skill's own commands produce: a Dynatrace token prefix, an
Authorization header with its value (`Authorization:`, `Authorization=`, a quoted JSON key, the
scheme right after the name), an Api-Token, Bearer or Basic scheme followed by an opaque value
of 20 or more characters, a URL carrying userinfo (`https://user:token@host`). Naming the header
or the scheme without a value passes, and so does a name or path that only contains a scheme
word (`basic-auth-service`, `src/basic/`).
"""
import argparse
import contextlib
import datetime
import hashlib
import json
import os
import pathlib
import re
import secrets
import stat
import sys

STATUSES = ("planned", "wired", "blocked", "skipped")
# The characters scripts/verify.sh takes for --env: a recorded name is always one it can ask with.
ENVIRONMENT = re.compile(r"[A-Za-z0-9._:+/@-]+")
STEPS = ("scan", "plan", "instrument", "verify", "handover")
# A line of `probe.sh deploy` as it prints it: the census prints no other characters.
DEPLOY_TARGET = re.compile(r"(?:helm|k8s|serverless): [A-Za-z0-9._/-]+")
# local: the verified stack ran on this machine; deployed: the plan named a deployed environment and the run started nothing.
SCOPES = ("local", "deployed")
LOCAL_ONLY = "locally only - no deployed environment has sent data yet"
# The closing summary's Reason set (references/closing-summary.md): one token per blocked or
# skipped row.
REASONS = (
    "build_failed",
    "unbuildable_on_host",
    "no_runtime",
    "registry_unreachable",
    "endpoint_unreachable",
    "port_busy",
    "no_endpoint",
    "no_token",
    "egress_blocked",
    "auth_rejected",
    "wire_rejected",
    "endpoint_rejected",
    "signal_unwired",
    "verify_absent",
    "verify_unreadable",
    "pii_withheld",
    "already_instrumented",
    "oneagent_sdk_inactive",
    "version_pinned",
    "out_of_scope",
    "not_started",
    "user_declined",
)
# A tripwire for the shapes the skill's own commands produce, not a secret scanner: the rule
# is to name a header, never reproduce it (Hard rule 1). Caught: a Dynatrace token prefix,
# which every Api-Token value carries; `Authorization` followed, after any run of separators,
# by `=`, `:` or a scheme (`Authorization:` in a curl line, `Authorization=` in an OTLP headers
# value, `{"Authorization": ...}`); an Api-Token, Bearer or Basic scheme standing as a word of
# its own followed, after any run of separators, by an opaque value (20+ token characters); an
# OTLP headers assignment. A scheme word joined to a longer name or path by `-`, `/` or a word
# character is no scheme (`basic-auth-service`, `src/basic/handler.go`), and naming the header
# or the scheme without a value ("the Authorization header was rejected", "sent Api-Token on a
# platform token; switch to Bearer") passes.
SECRET = re.compile(
    r"dt0[a-z][0-9]{2}\.|Authorization\W*([=:]|Api-Token|Bearer|Basic)"
    r"|(?<![\w/-])(Api-Token|Bearer|Basic)(?![\w/-])\W*[A-Za-z0-9._~+/=-]{20,}"
    r"|OTEL_EXPORTER_OTLP_HEADERS\s*[=:]",
    re.I,
)
# A remote URL's userinfo is where CI puts its job token (`https://gitlab-ci-token:<token>@host`); an
# ssh URL's bare user name (`ssh://git@host`) carries none, a `user:password` one does.
USERINFO = re.compile(r"(?<!ssh)://[^/\s]*@|(?<=ssh)://[^/\s]*:[^/\s]*@", re.I)
BODY_MAX = 64 * 1024  # a step report is a few tables; anything larger is raw output, which never goes in


def fail(msg: str) -> "NoReturn":
    print(f"state-update: {msg}", file=sys.stderr)
    sys.exit(1)


def record_dir(rec: pathlib.PurePosixPath) -> "int | None":
    """The record's directory, opened from the repository root one component at a time and never
    through a link, so a checkout changed after the checks cannot redirect the read or the write;
    None where the platform opens by path only (Windows), where the record is then left as it is."""
    if not {os.open, os.rename, os.stat, os.unlink} <= os.supports_dir_fd or not hasattr(os, "O_NOFOLLOW"):
        return None
    d = os.open(".", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in rec.parent.parts:
            nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=d)
            os.close(d)
            d = nxt
    except OSError:
        os.close(d)
        raise
    return d


def cell(text: object) -> str:
    """Agent text on one line of the readable record: a line break or a bare `|` would split a table row."""
    return re.sub(r"(\\*)\|", lambda m: m.group(1) * 2 + "\\|", " ".join(str(text).split()))


def code(text: object) -> str:
    """`cell` as a code span: a backtick in the value is no escape inside one, so the fence outgrows the longest run in it."""
    v = cell(text)
    fence = "`" * (max((len(r) for r in re.findall(r"`+", v)), default=0) + 1)
    pad = " " if v.startswith("`") or v.endswith("`") else ""
    return f"{fence}{pad}{v}{pad}{fence}"


def now() -> str:
    return datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %z")


def render(doc: dict, fallback_name: str) -> str:
    """The readable record: the shape of the guided variant's assets/run.md, filled from the run state."""
    steps, services = doc.get("steps", {}), doc["services"]
    repo = cell(USERINFO.sub("://", str(doc.get("repository") or "")))
    name = cell(re.sub(r"\.git$", "", re.split(r"[/:]", repo.rstrip("/"))[-1])) if repo else ""
    name = name or cell(fallback_name)
    finished = "handover" in steps
    counts = {s: sum(1 for svc in services if svc.get("status") == s) for s in ("wired", "blocked", "skipped")}
    current = "Finished" if finished else next(s for s in STEPS if s not in steps).title()

    def glyph(step: str) -> str:
        return "✓ " if step in steps else "– " if finished else ""

    # one paragraph per field: consecutive lines would render as a single run-on paragraph
    header = [
        f"**Repository** {code(repo or name)} @ {code(doc.get('revision') or 'unknown')}",
        f"**Started** {cell(doc.get('started', ''))}",
        *([f"**Environment** {code(doc['environment'])} (every `bluebox ask --env` of the run)"] if doc.get("environment") else []),
        *([f"**Verified** {LOCAL_ONLY}"] if doc.get("verified_scope") == "local" else []),
        *([f"**Verified** {code(doc.get('environment') or 'unnamed')} (deployed)"] if doc.get("verified_scope") == "deployed" else []),
        *(["**Deployment targets** " + " · ".join(code(t) for t in doc["deploy_targets"])] if doc.get("deploy_targets") else []),
        "**Progress** " + " · ".join(f"{glyph(s)}{s.title()}" for s in STEPS),
        # a skipped service is not to be wired: the count is over the services in scope
        f"**Status** {current} · {counts['wired']} of {len(services) - counts['skipped']} wired · {counts['blocked']} blocked · "
        f"{counts['skipped']} skipped",
    ]
    out = [
        f"# OpenTelemetry instrumentation run: {name}",
        "",
        "\n\n".join(header),
        "",
        "## Decisions",
        "",
        "| When | Step | Question | Choice | By |",
        "|---|---|---|---|---|",
        *(f"| {cell(x.get('when', ''))} | {cell(x.get('step', ''))} | {cell(x.get('question', ''))} | "
          f"{cell(x.get('choice', ''))} | {cell(x.get('by', ''))} |" for x in doc.get("decisions", [])),
    ]
    for n, step in enumerate(STEPS, 1):
        out += ["", f"## {n}. {step.title()}", ""]
        if step == "instrument":
            out += [f"Wired {counts['wired']} · Blocked {counts['blocked']} · Skipped {counts['skipped']}", "",
                    "| Service | State | Detail |", "|---|---|---|"]
            for svc in services:
                detail = " — ".join(x for x in (str(svc.get("reason") or ""), str(svc.get("detail") or "")) if x)
                out.append(f"| {cell(svc.get('name', ''))} | {cell(svc.get('status', ''))} | {cell(detail)} |")
            if steps.get(step):
                out += ["", steps[step]]
        else:
            out.append(steps.get(step) or ("_not run_" if finished else "_pending_"))
    return "\n".join(out) + "\n"


def progress(doc: dict, at: "datetime.datetime | None" = None) -> str:
    """The Instrument progress table a service call prints to stderr, counted from the record."""
    services = doc["services"]

    def count(status: str) -> int:
        return sum(1 for svc in services if svc.get("status") == status)

    head = f"**Wired {count('wired')} · In progress {count('planned')} · Blocked {count('blocked')}"
    head += f" · Skipped {count('skipped')}" if count("skipped") else ""
    try:
        start = datetime.datetime.strptime(str(doc.get("started", "")), "%Y-%m-%d %H:%M %z")
        head += f" · Elapsed {int(((at or datetime.datetime.now().astimezone()) - start).total_seconds() // 60)} min"
    except ValueError:
        pass
    def safe(text: str) -> str:
        # a record written before the check, or by hand, gets the same check as a new value before it reaches the terminal
        return "[withheld: looks like a credential]" if SECRET.search(text) or USERINFO.search(text) else text

    rows = []
    for svc in services:
        latest = " — ".join(x for x in (str(svc.get("reason") or ""), str(svc.get("detail") or "")) if x)
        state = "in progress" if svc.get("status") == "planned" else str(svc.get("status", ""))
        rows.append(f"| {cell(safe(str(svc.get('name', ''))))} | {cell(safe(state))} | {cell(safe(latest))} |")
    return "\n".join([head + "**", "", "| Service | State | Latest |", "|---|---|---|", *rows])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--record", default=".bluebox/instrumentation-run.json",
                    help="the run record (default: .bluebox/instrumentation-run.json, from the repository root)")
    ap.add_argument("--name", help="service name as the plan table names it")
    ap.add_argument("--status", choices=STATUSES)
    ap.add_argument("--file", action="append", default=[], metavar="PATH",
                    help="repository-relative path the plan row named; repeatable; the sha256 of its current content is recorded")
    ap.add_argument("--reason", default="",
                    help="blocked/skipped only: exactly one token from the closing summary's reason set (e.g. build_failed)")
    ap.add_argument("--detail", default="", help="the concrete detail the closing summary will carry")
    ap.add_argument("--step", choices=STEPS, help="the step whose report, as printed, comes on stdin")
    ap.add_argument("--environment", metavar="ENV",
                    help="the plan table's environment name (deployment.environment.name); verify.sh ask reads it from the record")
    ap.add_argument("--deploy-target", action="append", default=[], metavar="'KIND: PATH'",
                    help="a line of probe.sh deploy as printed (helm|k8s|serverless: <path>), repeatable; recorded at --step scan")
    ap.add_argument("--verified-scope", metavar="SCOPE",
                    help="what the verification reached: local (a stack on this machine) or deployed; recorded at --step verify")
    ap.add_argument("--decision", nargs=4, action="append", default=[], metavar=("STEP", "QUESTION", "CHOICE", "BY"),
                    help="an answer, repeatable: the step that asked, the question, the choice, who chose (developer, or default headless)")
    a = ap.parse_args()

    if (a.name is None) != (a.status is None):
        fail("--name and --status go together")
    if a.name is None and a.step is None and not a.decision and a.environment is None and not a.deploy_target \
            and a.verified_scope is None:
        fail("nothing to record: pass a service (--name, --status), a step report (--step), an answer (--decision), "
             "the environment name (--environment), a deploy target (--deploy-target) or the verified scope (--verified-scope)")
    if a.environment is not None and not ENVIRONMENT.fullmatch(a.environment):
        fail("--environment must match [A-Za-z0-9._:+/@-]+, the characters verify.sh takes for --env")
    for target in a.deploy_target:
        if not DEPLOY_TARGET.fullmatch(target):
            fail("--deploy-target takes a probe.sh deploy line as printed: helm|k8s|serverless, ': ', a path in A-Za-z0-9._/-")
    if a.verified_scope is not None and a.verified_scope not in SCOPES:
        fail(f"--verified-scope is {' or '.join(SCOPES)}")
    if a.status in ("blocked", "skipped") and not a.reason:
        fail(f"status {a.status} needs --reason (one token from the reason set)")
    if a.status in ("planned", "wired") and a.reason:
        fail(f"status {a.status} takes no --reason")
    if a.reason and a.reason not in REASONS and not re.fullmatch(r"other: \S.*", a.reason):
        fail(f"--reason is one token from the reason set ({', '.join(REASONS)}) or 'other: <free text>'")
    if any(step not in STEPS for step, *_ in a.decision):
        fail(f"--decision names the step that asked, one of {', '.join(STEPS)}")
    body = ""
    if a.step:
        raw = sys.stdin.buffer.read(BODY_MAX + 1)
        if len(raw) > BODY_MAX:
            fail(f"the {a.step} report is over {BODY_MAX} bytes: the record takes the step's tables and lines, never raw output")
        try:
            lines = raw.decode("utf-8").replace("\r\n", "\n").strip("\n").split("\n")
        except UnicodeDecodeError:
            fail(f"the {a.step} report is not UTF-8")
        if any(line != ">" and not line.startswith("> ") for line in lines):
            fail(f"every line of the {a.step} report opens with '> ' (a blank one is '>'), so no line of it can close "
                 "the heredoc early")
        body = "\n".join(line[2:] for line in lines).strip("\n").rstrip()
        if not body.strip():
            fail(f"--step {a.step} takes the step's report on stdin, in a quoted heredoc")
    for text in (a.detail, a.reason, a.name or "", body, *a.deploy_target, *(field for d in a.decision for field in d)):
        if SECRET.search(text) or USERINFO.search(text):
            fail("a token prefix, an Authorization value or a URL's userinfo would land in the record; name it, never reproduce it")

    root = pathlib.Path.cwd().resolve()
    rec = pathlib.PurePosixPath(a.record)
    if rec.is_absolute() or ".." in rec.parts:
        fail(f"--record {rec}: the record is a repository-relative path inside the repository")
    if not pathlib.Path(rec).is_file():
        fail(f"{rec} is missing: the record is written once the question is answered, before any service file changes")
    if root not in pathlib.Path(rec).resolve().parents:
        fail(f"{rec} resolves outside the repository: a record the checkout links elsewhere is not rewritten")
    try:
        d = record_dir(rec)
    except OSError as exc:
        fail(f"{rec}: a directory on its path is a link or changed ({exc.strerror}); a linked record is not rewritten")
    if d is None:
        fail(f"{rec} is left as it is: this platform opens files by path only, so a checkout changed mid-run could "
             "redirect the write; say so under Limitations and go on")
    import fcntl  # POSIX only, like the anchored write above

    fcntl.flock(d, fcntl.LOCK_EX)  # parallel calls take turns, each reading the record the last one wrote
    try:
        fd = os.open(rec.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=d)
    except OSError as exc:
        fail(f"{rec} cannot be opened as the record ({exc.strerror}); a linked record is not rewritten")
    with os.fdopen(fd, encoding="utf-8") as fh:
        try:
            doc = json.loads(fh.read())
        except (OSError, ValueError) as exc:
            fail(f"{rec} does not parse ({exc}); the record is stale, say so and start fresh")
    if (not isinstance(doc, dict) or not isinstance(doc.get("services"), list)
            or not isinstance(doc.get("steps", {}), dict) or not isinstance(doc.get("decisions", []), list)
            or not all(isinstance(x, dict) for x in doc["services"] + doc.get("decisions", []))
            or not all(isinstance(v, str) for v in doc.get("steps", {}).values())
            or not isinstance(doc.get("environment", ""), str)
            or not isinstance(doc.get("deploy_targets", []), list) or not all(isinstance(t, str) for t in doc.get("deploy_targets", []))
            or not isinstance(doc.get("verified_scope", ""), str)
            or any(not DEPLOY_TARGET.fullmatch(t) or SECRET.search(t) or USERINFO.search(t) for t in doc.get("deploy_targets", []))
            or doc.get("verified_scope", "") not in ("", *SCOPES)):
        fail(f"{rec} carries no services list, or steps and decisions of another shape; the record is stale, say so and start fresh")
    readable = rec.with_suffix(".md").name
    with contextlib.suppress(FileNotFoundError):
        if not stat.S_ISREG(os.stat(readable, dir_fd=d, follow_symlinks=False).st_mode):
            fail(f"{rec.with_suffix('.md')} is a link or not a regular file: a linked record is not rewritten")

    if a.name is not None:
        files = []
        for f in a.file:
            p = pathlib.PurePosixPath(f)
            if p.is_absolute() or ".." in p.parts:
                fail(f"--file {f}: paths are repository-relative and inside the repository")
            if root not in pathlib.Path(f).resolve().parents:
                fail(f"--file {f}: resolves outside the repository (a symlink out of the checkout is not recorded)")
            try:
                digest = hashlib.sha256(pathlib.Path(f).read_bytes()).hexdigest()
            except OSError as exc:
                fail(f"--file {f}: cannot read ({exc})")
            files.append({"path": str(p), "sha256": digest})

        hit = [svc for svc in doc["services"] if svc.get("name") == a.name]
        if not hit:
            fail(f"{rec} has no service {a.name!r}; the plan table names every service before it is recorded")
        for svc in hit:
            svc["status"], svc["reason"], svc["detail"] = a.status, a.reason, a.detail
            if files or "files" not in svc:
                svc["files"] = files
    doc.setdefault("started", now())
    if "repository" in doc:
        doc["repository"] = USERINFO.sub("://", str(doc["repository"]))
    if a.environment is not None:
        recorded = doc.get("environment")
        if recorded not in (None, a.environment) and not any(by == "developer" for *_, by in a.decision):
            fail(f"{rec} names environment {recorded!r}; changing it to {a.environment!r} is a re-scope only the "
                 "developer makes: pass their answer as --decision ... developer in the same call (a headless run never "
                 "re-scopes itself)")
        doc["environment"] = a.environment
    if a.deploy_target:
        doc["deploy_targets"] = list(dict.fromkeys(a.deploy_target))
    if a.verified_scope is not None:
        doc["verified_scope"] = a.verified_scope
    if a.step:
        doc["steps"] = {**doc.get("steps", {}), a.step: body}
    if a.decision:
        when = now()
        doc["decisions"] = [*doc.get("decisions", []), *({"when": when, "step": step, "question": question, "choice": choice, "by": by}
                                                         for step, question, choice, by in a.decision)]

    # fresh names beside the records, created and renamed through the same directory: each replace stays
    # atomic and no link the checkout plants is written through; both temps exist before either replace,
    # so a failed write leaves both records as they were (a failed second replace, the readable one a call behind)
    written = []
    try:
        for name, content in ((rec.name, json.dumps(doc, indent=2) + "\n"), (readable, render(doc, root.name))):
            tmp = f"{name}.{secrets.token_hex(8)}.new"
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=d)
            written.append((tmp, name))
            with os.fdopen(fd, "w", encoding="utf-8") as out:
                out.write(content)
        for tmp, name in written:
            os.replace(tmp, name, src_dir_fd=d, dst_dir_fd=d)  # a reader sees the old record or the new one
    except BaseException:
        for tmp, _ in written:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(tmp, dir_fd=d)
        raise
    finally:
        os.close(d)
    done = sum(1 for svc in doc["services"] if svc.get("status") == "wired")
    what = [f"{a.name}: {a.status}{' (' + a.reason + ')' if a.reason else ''}"] if a.name is not None else []
    what += [f"environment {a.environment}"] if a.environment is not None else []
    what += [f"{len(doc['deploy_targets'])} deploy target(s)"] if a.deploy_target else []
    what += [f"verified {a.verified_scope}"] if a.verified_scope is not None else []
    what += [f"step {a.step}"] if a.step else []
    what += [f"decision {step}" for step, *_ in a.decision]
    print(f"{', '.join(what)}; {done} of {len(doc['services'])} wired")
    if a.name is not None:
        # stderr: a batch that keeps one stdout line per call (`| head -1`) still shows the table
        sys.stdout.flush()  # merged with 2>&1, the one stdout line stays first
        print(progress(doc), file=sys.stderr)


if __name__ == "__main__":
    main()
