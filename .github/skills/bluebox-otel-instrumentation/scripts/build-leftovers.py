#!/usr/bin/env python3
"""What this run's image builds left on the developer's container runtime, and the one way to remove it.

Verify rebuilds the repository's images, each rebuild leaves the image it replaced untagged, and a
failed legacy-builder step leaves its container. The skill never removes what it did not create
(Hard rule 12): `snapshot` and `report` only list, inspect and measure; `remove` is the only writer.

    python3 <skill dir>/scripts/build-leftovers.py snapshot --runtime docker|podman .bluebox/build-snapshot.json
    python3 <skill dir>/scripts/build-leftovers.py report --since .bluebox/build-snapshot.json [--json]
    python3 <skill dir>/scripts/build-leftovers.py remove --since .bluebox/build-snapshot.json --ids <id>[,<id>...] [--json]

`snapshot`, right before the run's first image build, records every image and container id the
runtime has and the `started` of the run record beside it. A runtime that does not answer gets no
snapshot (exit 1), never an empty one.

`report` prints one line (`line()`) for what appeared since the snapshot, the size a floored lower
bound. With no trustworthy answer (no snapshot, not this run's, runtime silent, another build
running, unreadable sizes) it prints nothing on stdout, says why on stderr and exits 2.

`remove` takes the ids `report --json` listed and removes, by exact id and in passes, those still
attributed to this run and made since it started by the runtime's own clock. Exit 2 with nothing on stdout when nothing was removed; exit 1 after
the runtime fell silent mid-removal.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone

RUNTIMES = ("docker", "podman")
STEP_PREFIXES = ("/bin/sh -c", "/bin/bash -c")  # what the legacy builder runs a Dockerfile step as
COMPOSE = "com.docker.compose.project"
# `run()` takes only these: listings, inspects and the disk-usage table. The one write path is
# `write()` below, reached only from `remove`, by exact id.
READ_ONLY = (("ps",), ("images",), ("container", "inspect"), ("image", "inspect"), ("system", "df"))
# `ps` takes only these: `--external` adds the containers buildah made (a failed `podman build`
# step leaves one), which `podman ps -a` never shows and `podman container inspect` cannot resolve.
PS_FLAGS = {"-aq", "-a", "-q", "--external", "--format", "json"}
TIMEOUT = 60  # seconds per runtime call: a hung daemon must not hold the summary
WRITE_VERBS = ("rm", "rmi")
EXACT_ID = re.compile(r"[0-9a-f]{12}")
RECORD = "instrumentation-run.json"  # the run record state-update.py writes beside the snapshot


class DaemonSilent(Exception):
    """The runtime did not answer. Not the same as a runtime with nothing on it: every caller has
    to tell those apart, because "nothing on it" is what turns a delta into the whole machine."""


class Unreadable(Exception):
    """The runtime answered in a shape this script does not know: no number beats a wrong one."""


def run(args: list[str], binary: str, required: bool = False) -> str:
    if tuple(args[:2]) not in READ_ONLY and tuple(args[:1]) not in READ_ONLY:
        raise ValueError(f"not a read-only call: {args[:2]}")
    if args[:1] == ["ps"] and not set(args[1:]) <= PS_FLAGS:
        raise ValueError(f"not a read-only listing: {args}")
    try:
        proc = subprocess.run([binary, *args], capture_output=True, text=True, timeout=TIMEOUT,
                              stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as err:
        if required:
            raise DaemonSilent(f"{binary} {' '.join(args[:2])}: {err}") from err
        return ""
    if proc.returncode != 0:
        if required:
            raise DaemonSilent(f"{binary} {' '.join(args[:2])} exited {proc.returncode}: {proc.stderr.strip()[:200]}")
        return ""
    return proc.stdout


def short(ident: str) -> str:
    """The 12 hex characters a listing prints. `ps -aq` truncates to 12 while `inspect` returns 64,
    with a `sha256:` prefix on docker and without one on podman, so every comparison goes through this."""
    return (ident or "").split(":")[-1][:12]


# The whole line a runtime writes for an id it cannot resolve, and only that line:
#   Error response from daemon: No such image: 708abec0a060:latest
#   Error response from daemon: No such container: aaaaaaaaaaaa
#   error: no such object: aaaaaaaaaaaa
# Anchored at both ends: a miss with a real failure appended is an error.
MISS = re.compile(r"(?:Error response from daemon|error): no such (?:image|container|object): [A-Za-z0-9._/:@-]+",
                  re.IGNORECASE)


# A refusal (in use, tagged since) has stderr text; a dead daemon cannot connect or is silent.
SILENT = re.compile(r"cannot connect|unable to connect|is the docker daemon running|connection refused|no such host", re.I)


def inspect(kind: str, ids: list[str], binary: str, partial: bool = False) -> list[dict]:
    """A runtime exits 1 when any one id no longer resolves - a container that ended between the
    listing and here - while still printing the records it did find. By default that answer is
    refused: read as complete, it would drop a live container out of `held` and make the image it
    uses look like a leftover. `partial=True` accepts it when every stderr line is a miss, for a
    caller that fewer records can only make more careful."""
    if kind not in ("container", "image"):
        raise ValueError(f"not an inspect kind: {kind!r}")
    if not ids:
        return []
    try:
        proc = subprocess.run([binary, kind, "inspect", *ids], capture_output=True, text=True, timeout=TIMEOUT,
                              stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as err:
        raise DaemonSilent(f"{kind} inspect: {err}") from err
    if proc.returncode != 0:
        errors = [ln.strip() for ln in proc.stderr.splitlines() if ln.strip()]
        if not partial or not errors or not all(MISS.fullmatch(ln) for ln in errors):
            raise DaemonSilent(f"{kind} inspect exited {proc.returncode}: {proc.stderr.strip()[:200]}")
    try:
        records = json.loads(proc.stdout or "")
    except json.JSONDecodeError as err:
        raise DaemonSilent(f"{kind} inspect: {err}") from err
    if not isinstance(records, list):
        raise DaemonSilent(f"{kind} inspect answered with a {type(records).__name__}")
    return records


def podman(binary: str) -> bool:
    return os.path.basename(binary) == "podman"


def ps_all(binary: str) -> list[str]:
    """Every container id, buildah's included on podman."""
    return ["ps", "-a", "-q", "--external"] if podman(binary) else ["ps", "-aq"]


def ids(args: list[str], binary: str) -> list[str]:
    return sorted({short(i) for i in run(args, binary, required=True).split()})


def snapshot(binary: str, runtime: str, every_image: bool = True) -> dict:
    """The ids that already exist, so nothing older than the run is ever counted. `images` are the
    dangling ones; `all_images`, every image, tagged or not, which is what keeps the developer's own
    image out once a rebuild untags it. Raises DaemonSilent rather than return an empty snapshot."""
    state = {"ok": True, "runtime": runtime,
             "images": ids(["images", "-q", "-f", "dangling=true"], binary),
             "containers": ids(ps_all(binary), binary)}
    if every_image:
        state["all_images"] = ids(["images", "-aq"], binary)
    return state


# A creation time as RFC 3339, with a Z or a local offset and more fractional digits than
# fromisoformat accepts
STAMP = re.compile(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.\d+)?(Z|z|[+-]\d{2}:?\d{2})?")


def created_at(created: str) -> datetime | None:
    m = STAMP.match((created or "").strip())
    if not m:
        return None
    made = datetime.strptime(m.group(1), "%Y-%m-%dT%H:%M:%S")
    zone = m.group(2)
    if zone in (None, "Z", "z"):
        return made.replace(tzinfo=timezone.utc)
    offset = timedelta(hours=int(zone[1:3]), minutes=int(zone[-2:])) * (1 if zone[0] == "+" else -1)
    return made.replace(tzinfo=timezone(offset))


def age_seconds(created: str) -> float | None:
    made = created_at(created)
    return None if made is None else (datetime.now(timezone.utc) - made).total_seconds()


def _made_since(created: str, not_before: datetime | None) -> bool:
    if not_before is None:
        return True
    made = created_at(created)
    return made is not None and made >= not_before  # the runtime's own clock, not the snapshot file


def _age_ok(created: str, older_than: float | None) -> bool:
    if older_than is None:
        return True
    age = age_seconds(created)
    return age is not None and age >= older_than  # an unreadable stamp is never a candidate


def _labels(record: dict) -> dict:
    # docker keeps an image's labels under Config; podman also repeats them at the top level
    return (record.get("Config") or {}).get("Labels") or record.get("Labels") or {}


def podman_containers(binary: str) -> tuple[list[dict], list[dict]]:
    """podman's containers as (inspected, external). A buildah container (state `storage`) is in the
    listing only: inspect answers `no such container` for it, so its fields come from the listing."""
    try:
        listed = json.loads(run(["ps", "-a", "--external", "--format", "json"], binary, required=True))
    except json.JSONDecodeError as err:
        raise DaemonSilent(f"ps --external: {err}") from err
    if not isinstance(listed, list) or not all(isinstance(c, dict) and isinstance(c.get("Id"), str) for c in listed):
        raise DaemonSilent("ps --external answered in an unknown shape")
    external, own = [], []
    for c in listed:
        if str(c.get("State", "")).lower() != "storage":
            own.append(c["Id"])
            continue
        made = c.get("Created")
        if not isinstance(made, (int, float)):
            raise DaemonSilent(f"ps --external: no creation time for {short(c['Id'])}")
        names = c.get("Names") or [""]
        external.append({"Id": c["Id"], "Name": str(names[0]), "Command": c.get("Command") or [],
                         "Labels": c.get("Labels") or {}, "Image": c.get("ImageID") or "",
                         "Created": datetime.fromtimestamp(made, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")})
    return inspect("container", own, binary), external


def find(before: dict | None = None, older_than: float | None = None, binary: str = "docker",
         count_compose_images: bool = True) -> dict:
    """The build leftovers on the runtime now that `before` does not hold. A container counts when it
    is exited or created, ran a Dockerfile step and carries no compose project label; an image when it
    is dangling and no surviving container uses it. `count_compose_images=False` also leaves out an
    image compose built (the label is on every image `compose build` makes, superseded ones too)."""
    seen_images = {short(i) for key in ("images", "all_images") for i in (before or {}).get(key) or []}
    seen_containers = {short(c) for c in (before or {}).get("containers") or []}

    if podman(binary):
        all_containers, external = podman_containers(binary)
    else:
        all_containers, external = inspect("container", run(ps_all(binary), binary, required=True).split(), binary), []
    containers, in_flight = [], []
    for c in external:
        if short(c["Id"]) in seen_containers or _labels(c).get(COMPOSE) or c["Command"] != ["buildah"]:
            continue
        if _age_ok(c["Created"], older_than):
            containers.append({"id": c["Id"], "name": c["Name"], "created": c["Created"], "external": True})
    for c in all_containers:
        cid = c.get("Id", "")
        cmd = " ".join((c.get("Config") or {}).get("Cmd") or [])
        state = (c.get("State") or {}).get("Status", "")
        if short(cid) in seen_containers or _labels(c).get(COMPOSE):
            continue
        if state == "running" and cmd.startswith(STEP_PREFIXES):
            in_flight.append(cid)   # a build in progress the snapshot did not know: not this run's
            continue
        if state not in ("exited", "created") or not cmd.startswith(STEP_PREFIXES):
            continue
        if not _age_ok(c.get("Created", ""), older_than):
            continue
        # the step's command is not carried: a Dockerfile step runs whatever the build put in it -
        # a signed URL, a token in a header - and this output can end up in a summary or a report
        containers.append({"id": cid, "name": (c.get("Name") or "").lstrip("/"), "created": c.get("Created", "")})

    # an image any surviving container still uses is not a leftover, whoever owns that container
    doomed = {c["id"] for c in containers}
    held = {short(c.get("Image") or "") for c in all_containers + external if c.get("Id") not in doomed}
    images = []
    dangling = ids(["images", "-q", "-f", "dangling=true"], binary)
    for img in inspect("image", [i for i in dangling if i not in seen_images], binary):
        iid = short(img.get("Id", ""))
        if iid in held or (not count_compose_images and _labels(img).get(COMPOSE)):
            continue
        if not _age_ok(img.get("Created", ""), older_than):
            continue
        images.append({"id": iid, "size": img.get("Size", 0), "created": img.get("Created", ""),
                       "parent": short(img.get("Parent") or "")})
    return {"attributed": before is not None, "containers": containers, "images": images, "in_flight": in_flight}


def write(verb: str, ident: str, binary: str, storage: bool = False) -> bool:
    """Remove one container (`rm`, or `rm --storage` for a buildah one podman cannot resolve) or image
    (`rmi`) by the exact id the report printed: no force, no filter, no listing. False when the runtime
    refused it; a runtime that did not answer raises."""
    if verb not in WRITE_VERBS or not EXACT_ID.fullmatch(ident) or (storage and verb != "rm"):
        raise ValueError(f"not an exact-id removal: {verb} {ident}")
    argv = [binary, verb, *(["--storage"] if storage else []), ident]
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=TIMEOUT, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as err:
        raise DaemonSilent(f"{binary} {verb}: {err}") from err
    if proc.returncode != 0 and (SILENT.search(proc.stderr) or not proc.stderr.strip()):
        raise DaemonSilent(f"{binary} {verb} exited {proc.returncode}: {proc.stderr.strip()[:200]}")
    return proc.returncode == 0


def ancestors_of(images: list[dict], binary: str, depth: int = 200) -> set[str]:
    """Every image above the candidates in the legacy builder's parent chain, read while the
    records still exist: once a leaf is removed docker may take the parent record with it and
    list the grandparent as the next leaf, so the set is taken up front, not one level at a
    time. The first level is the `parent` the listing already recorded; the rest is walked."""
    ids = {i["id"] for i in images}
    seen: set[str] = set(ids)
    frontier = [i["parent"] for i in images if i.get("parent") and i["parent"] not in seen]
    for _ in range(depth):
        if not frontier:
            break
        parents = []
        # a gone parent ends its branch; only silence stops the walk
        records = inspect("image", [f for f in frontier if f not in seen], binary, partial=True)
        for rec in records:
            seen.add(short(rec.get("Id", "")))
            p = short(rec.get("Parent") or "")
            if p and p not in seen:
                parents.append(p)
        frontier = parents
    return seen - ids


def remove_found(found: dict, binary: str, into: dict) -> int:
    """Containers first: an image a leftover container holds cannot go while it exists. Appends each id
    to `into`'s containers, images or refused as it goes, so a runtime that falls silent mid-pass leaves
    an exact account. Returns how many were removed. A refusal is named, never counted."""
    gone = 0
    for kind, verb, items in (("containers", "rm", found["containers"]), ("images", "rmi", found["images"])):
        for x in items:
            ident = short(x["id"])
            if write(verb, ident, binary, storage=bool(x.get("external"))):
                into[kind].append(ident)
                gone += 1
            else:
                into["refused"].append(ident)
    return gone


def remove_in_passes(before: dict | None, binary: str, wanted: set[str] | None = None,
                     older_than: float | None = None, count_compose_images: bool = True, limit: int = 64,
                     not_before: datetime | None = None) -> dict:
    """The runtime lists only the leaves of a step chain as dangling, so removing a leaf makes its
    parent the next one. Pass one takes the attributed candidates (only those in `wanted`, when
    given); before it removes anything it reads their whole ancestor set, and every later pass takes
    only newly dangling images inside that set, so nothing the first pass did not lead to is touched.
    Stops when a pass finds nothing, when the runtime refused all of a pass, or at `limit`."""
    out = {"containers": [], "images": [], "refused": [], "passes": 0, "in_flight": False, "capped": False}
    allowed: set[str] | None = None
    while out["passes"] < limit:
        try:
            found = find(before, older_than, binary, count_compose_images)
        except DaemonSilent as err:
            err.removed_so_far = out   # type: ignore[attr-defined]
            raise
        if found["in_flight"]:
            out["in_flight"] = True
            return out
        # the snapshot file is writable by the build; what the runtime made before the run is never this run's
        found = {**found, "containers": [c for c in found["containers"] if _made_since(c.get("created", ""), not_before)],
                 "images": [i for i in found["images"] if _made_since(i.get("created", ""), not_before)]}
        if allowed is None:
            if wanted is not None:
                found = {**found, "containers": [c for c in found["containers"] if short(c["id"]) in wanted],
                         "images": [i for i in found["images"] if short(i["id"]) in wanted]}
        else:
            tried = {*out["containers"], *out["images"], *out["refused"]}   # a refused one stays listed: once
            found = {**found, "containers": [], "images": [i for i in found["images"]
                                                           if short(i["id"]) in allowed and short(i["id"]) not in tried]}
        if not found["containers"] and not found["images"]:
            break
        if allowed is None:
            try:
                allowed = ancestors_of(found["images"], binary)
            except DaemonSilent as err:
                raise DaemonSilent(f"{err}; the ancestor set could not be read, nothing removed") from err
        out["passes"] += 1
        try:
            gone = remove_found(found, binary, out)
        except DaemonSilent as err:
            err.removed_so_far = out   # type: ignore[attr-defined]
            raise
        if not gone:
            break   # the runtime refused the whole pass: nothing new will surface
        if not allowed:
            break
    else:
        # the limit was reached, not the same as work left: list once more, same arguments
        try:
            left = find(before, older_than, binary, count_compose_images)["images"]
        except DaemonSilent as err:
            err.removed_so_far = out   # type: ignore[attr-defined]
            raise
        tried = {*out["containers"], *out["images"], *out["refused"]}
        out["capped"] = any(short(i["id"]) in (allowed or set()) and short(i["id"]) not in tried for i in left)
    return out


UNITS = {"B": 1, "KB": 10**3, "MB": 10**6, "GB": 10**9, "TB": 10**12, "PB": 10**15}
SIZE = re.compile(r"(\d+(?:\.\d+)?)\s*([kKMGTP]?B)")
COLUMNS = re.compile(r"\S+(?: \S+)*")  # a column value holds single spaces at most ("16 hours ago")


def to_bytes(text: str) -> int:
    """A size as docker and podman print it, decimal units: `52.72MB`, `24.91kB`, `0B`."""
    m = SIZE.fullmatch(text.strip())
    if not m:
        raise Unreadable(f"not a size: {text!r}")
    return round(float(m.group(1)) * UNITS[m.group(2).upper()])


def unique_sizes(binary: str) -> dict[str, int]:
    """Each image's UNIQUE SIZE from `system df -v`, by 12-character id: the bytes no other image
    shares. The table is read rather than `--format json`, which podman refuses next to `-v`."""
    out = run(["system", "df", "-v"], binary, required=True)
    lines = out.splitlines()
    try:
        start = next(i for i, ln in enumerate(lines) if ln.strip().startswith("Images space usage"))
        header = next(i for i in range(start + 1, len(lines)) if lines[i].strip())
    except StopIteration as err:
        raise Unreadable("no images table in system df -v") from err
    names = [col.group(0) for col in COLUMNS.finditer(lines[header])]
    if "IMAGE ID" not in names or "UNIQUE SIZE" not in names:
        raise Unreadable(f"system df -v header lacks IMAGE ID or UNIQUE SIZE ({len(names)} columns)")
    sizes = {}
    for number, row in enumerate(lines[header + 1:], start=1):
        if not row.strip():
            break
        cells = [col.group(0) for col in COLUMNS.finditer(row)]
        if len(cells) != len(names):
            raise Unreadable(f"system df -v row {number} has {len(cells)} columns, the header {len(names)}")
        sizes.setdefault(short(cells[names.index("IMAGE ID")]), to_bytes(cells[names.index("UNIQUE SIZE")]))
    return sizes


def measure(found: dict, binary: str) -> dict:
    """`found` with each image's unique size and their total as `bytes`; `bytes` is None when the
    table could not be read or lacks one of the images."""
    try:
        sizes = unique_sizes(binary)
    except (DaemonSilent, Unreadable) as err:
        return {**found, "bytes": None, "why": str(err)}
    if any(i["id"] not in sizes for i in found["images"]):
        return {**found, "bytes": None, "why": "an image is missing from system df -v"}
    images = [{**i, "unique": sizes[i["id"]]} for i in found["images"]]
    return {**found, "images": images, "bytes": sum(i["unique"] for i in images)}


def floor_gb(size: float) -> str:
    """`size` bytes in GB floored to one decimal: a lower bound must never be rounded up."""
    tenths = math.floor(size / 1e8)
    return f"{tenths // 10}.{tenths % 10}"


def line(found: dict) -> str:
    if not found["images"] and not found["containers"]:
        return "Build leftovers: none"
    counts = f"Build leftovers: {len(found['images'])} image(s), {len(found['containers'])} container(s)"
    size = floor_gb(found["bytes"])
    if size == "0.0":
        return f"{counts} from this run's rebuilds"
    return f"{counts}, at least {size} GB from this run's rebuilds"


def write_snapshot(path: str, state: dict) -> None:
    """Replace `path`, never through a link: a `.bluebox` or a snapshot the repository planted as a
    link must not redirect the write."""
    parent, name = os.path.split(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
        if os.path.islink(parent):
            raise OSError(f"{parent} is a link")
    tmp = os.path.join(parent, f".{name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(state, fh)
        if os.path.islink(path):
            raise OSError(f"{path} is a link")
        os.replace(tmp, path)
    except BaseException:
        if os.path.lexists(tmp):
            os.unlink(tmp)
        raise


def read_snapshot(path: str) -> dict:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, encoding="utf-8") as fh:
        state = json.load(fh)
    if not isinstance(state, dict) or state.get("ok") is not True or state.get("runtime") not in RUNTIMES:
        raise ValueError("not a snapshot the runtime answered")
    for key in ("images", "containers", "all_images"):
        held = state.get(key)
        if not isinstance(held, list) or not all(isinstance(i, str) for i in held):
            raise ValueError(f"snapshot has no list of ids under {key!r}")
    return state


NO_RECORD = object()


def run_started(snapshot_path: str):
    """The `started` of the run record beside the snapshot, None when it has none, NO_RECORD when there
    is no record. Read like the snapshot, never through a link; an unreadable record raises."""
    parent = os.path.dirname(snapshot_path)
    if parent and os.path.islink(parent):
        raise OSError(f"{parent} is a link")
    try:
        fd = os.open(os.path.join(parent, RECORD), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except FileNotFoundError:
        return NO_RECORD
    with os.fdopen(fd, encoding="utf-8") as fh:
        doc = json.load(fh)
    if not isinstance(doc, dict):
        raise ValueError(f"{RECORD} is not a run record")
    return doc.get("started")


def this_runs_snapshot(since: str, runtime: str | None) -> dict | None:
    """The snapshot at `since` when it is usable and this run's (and `runtime`'s, when given); otherwise
    the reason on stderr and None."""
    try:
        before = read_snapshot(since)
    except (OSError, ValueError) as err:
        print(f"build-leftovers: no usable snapshot at {since}: {err}", file=sys.stderr)
        return None
    if runtime and runtime != before["runtime"]:
        print(f"build-leftovers: the snapshot is {before['runtime']}'s, not {runtime}'s", file=sys.stderr)
        return None
    try:
        started = run_started(since)
    except (OSError, ValueError) as err:
        print(f"build-leftovers: the run record beside {since} is unreadable: {err}", file=sys.stderr)
        return None
    # no record, no tie to this run: a later run would claim an old snapshot's whole delta
    if started is NO_RECORD or not isinstance(started, str) or not started:
        print(f"build-leftovers: no run record with a start time beside {since}", file=sys.stderr)
        return None
    if before.get("started") != started:
        print(f"build-leftovers: the snapshot at {since} is not this run's (started "
              f"{before.get('started', 'unrecorded')}, the run record says {started})", file=sys.stderr)
        return None
    return before


def removed_line(done: dict, freed: int | None) -> str:
    """`remove`'s one line: a size only when `system df -v` gave one, and a cap that left work is said aloud."""
    size = "size unknown" if freed is None else f"at least {floor_gb(freed)} GB"
    text = f"Build leftovers removed: {len(done['images'])} image(s), {len(done['containers'])} container(s), {size}"
    if done["refused"]:
        text += f"; kept {len(done['refused'])}, the runtime refused: {', '.join(done['refused'])}"
    if done["capped"]:
        text += f"; stopped after {done['passes']} passes with more left, which `report` lists"
    return text


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="build-leftovers.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("snapshot")
    s.add_argument("--runtime", required=True, choices=RUNTIMES)
    s.add_argument("path")
    r = sub.add_parser("report")
    r.add_argument("--since", required=True)
    r.add_argument("--runtime", choices=RUNTIMES, help="refuse a snapshot another runtime took")
    r.add_argument("--json", action="store_true")
    m = sub.add_parser("remove")
    m.add_argument("--since", required=True)
    m.add_argument("--ids", required=True, help="the ids `report --json` listed, comma-separated")
    m.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    if args.cmd == "snapshot":
        try:
            state = snapshot(args.runtime, args.runtime)
        except DaemonSilent as err:
            state, why = {"ok": False, "runtime": args.runtime}, err
        else:
            why = None
        try:
            started = run_started(args.path)
        except (OSError, ValueError):
            started = None
        state["started"] = None if started is NO_RECORD else started   # ties the snapshot to this run
        try:
            write_snapshot(args.path, state)   # a failed one replaces any older snapshot at the path
        except OSError as err:
            print(f"build-leftovers: no snapshot written: {err}", file=sys.stderr)
            return 1
        if why is not None:
            print(f"build-leftovers: no snapshot, {args.runtime} did not answer: {why}", file=sys.stderr)
            return 1
        return 0

    if args.cmd == "remove":
        wanted = {w.strip() for w in args.ids.split(",") if w.strip()}
        if not wanted or not all(EXACT_ID.fullmatch(w) for w in wanted):
            print("build-leftovers: --ids takes the 12-character ids `report --json` printed", file=sys.stderr)
            return 2
        before = this_runs_snapshot(args.since, None)
        if before is None:
            return 2
        rt = before["runtime"]
        try:
            # the record keeps only the minute: all of it counts as before the run
            not_before = datetime.strptime(before["started"], "%Y-%m-%d %H:%M %z") + timedelta(minutes=1)
        except (TypeError, ValueError):
            print(f"build-leftovers: the run's start time {before.get('started')!r} is unreadable; nothing removed",
                  file=sys.stderr)
            return 2
        try:
            sized = measure(find(before, None, rt), rt)   # unique sizes, before anything goes
            sizes = {short(i["id"]): i.get("unique", 0) for i in sized["images"]}
            if not any(short(x["id"]) in wanted and _made_since(x.get("created", ""), not_before)
                       for x in sized["images"] + sized["containers"]):
                print("build-leftovers: none of those ids is this run's leftover now; nothing removed", file=sys.stderr)
                return 2
            done = remove_in_passes(before, rt, wanted, not_before=not_before)
            code = 0
        except DaemonSilent as err:
            done = getattr(err, "removed_so_far", None)
            print(f"build-leftovers: {rt} did not answer: {err}", file=sys.stderr)
            if not done or not (done["images"] or done["containers"]):
                return 2   # nothing went: no line, the reason on stderr
            code = 1
        if done["in_flight"]:
            gone = bool(done["images"] or done["containers"])
            print("build-leftovers: another build is running on this runtime; "
                  + ("nothing more removed" if gone else "nothing removed"), file=sys.stderr)
            if not gone:
                return 2
        freed = None if sized["bytes"] is None else sum(sizes.get(i, 0) for i in done["images"])
        if args.json:
            print(json.dumps({"runtime": rt, "containers": done["containers"], "images": done["images"],
                              "refused": done["refused"], "bytes": freed, "bound": "lower", "passes": done["passes"],
                              "capped": done["capped"]}))
        else:
            print(removed_line(done, freed))
        return code

    before = this_runs_snapshot(args.since, args.runtime)
    if before is None:
        return 2
    try:
        found = find(before, None, before["runtime"])
    except DaemonSilent as err:
        print(f"build-leftovers: {before['runtime']} did not answer: {err}", file=sys.stderr)
        return 2
    if found["in_flight"]:
        print("build-leftovers: another build is running on this runtime; its images and this run's "
              "cannot be told apart", file=sys.stderr)
        return 2
    found = measure(found, before["runtime"])
    if found["bytes"] is None:
        print(f"build-leftovers: sizes unreadable: {found['why']}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps({"runtime": before["runtime"], "bytes": found["bytes"], "bound": "lower", "line": line(found),
                          "images": [{"id": i["id"], "unique": i["unique"]} for i in found["images"]],
                          "containers": [{"id": short(c["id"]), "name": c["name"]} for c in found["containers"]]}))
    else:
        print(line(found))
    return 0


if __name__ == "__main__":
    sys.exit(main())
