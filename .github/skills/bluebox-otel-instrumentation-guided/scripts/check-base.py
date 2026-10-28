#!/usr/bin/env python3
"""Check that the hub installed beside this skill is one it can run on.

This variant follows the SKILL.md of the skill its `metadata.base` names, installed beside it,
as its run contract, so an older copy of that skill in the same skills directory would run
this variant's guidance on rules it was not written for. The minimum is this skill's own
`metadata.base_min_version`.
Prints one line: `ok: <base> <version> at <dir>` and exit 0, where <dir> is the base's resolved
directory and the only path the variant reads the base through, or `stop: …` and exit 1.

Usage:
  python3 <this skill's base directory>/scripts/check-base.py
"""
from __future__ import annotations

import os
import re
import sys

SEMVER = re.compile(r"(\d+)\.(\d+)\.(\d+)")
# One skill directory name, never a path: the base is looked up beside this skill.
SKILL_NAME = re.compile(r"[a-z0-9][a-z0-9-]*")
REINSTALL = "reinstall this skill: run `bluebox skills refresh`, or `npx skills add bluebox-hq/skills` if npx installed it"


def metadata_value(skill_md: str, key: str) -> str | None:
    """`metadata.<key>` from a SKILL.md's flat `metadata:` block, unquoted, or None; stdlib only."""
    with open(skill_md, encoding="utf-8") as f:
        lines = f.read().splitlines()
    if not lines or lines[0].rstrip() != "---":
        return None
    in_metadata, indent = False, None
    for line in lines[1:]:
        if line.rstrip() == "---":
            break
        if not line.strip():
            continue
        if not line[0].isspace():
            in_metadata, indent = line.rstrip() == "metadata:", None
            continue
        lead = len(line) - len(line.lstrip())
        indent = lead if indent is None else indent
        name, sep, value = line.strip().partition(":")
        if in_metadata and lead == indent and sep and name == key:
            return value.strip().strip("\"'")
    return None


def parse(version: str | None) -> tuple[int, int, int] | None:
    m = SEMVER.fullmatch(version or "")
    return (int(m[1]), int(m[2]), int(m[3])) if m else None


def inside(root: str, real: str) -> bool:
    try:
        return os.path.commonpath([root, real]) == root
    except ValueError:  # different drives on Windows: outside by definition
        return False


def first_escape(top: str, root: str) -> tuple[str, str] | None:
    """(path, real path) of the first entry under `top`, itself included, outside `root`; follows dir links, each real dir once."""
    seen, stack = set(), [top]
    while stack:
        path = stack.pop()
        real = os.path.realpath(path)
        if not inside(root, real):
            return path, real
        if os.path.isdir(real) and real not in seen:
            seen.add(real)
            stack.extend(os.path.join(path, name) for name in sorted(os.listdir(path)))
    return None


def main() -> int:
    skill_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    skills_dir = os.path.dirname(skill_dir)
    own_md = os.path.join(skill_dir, "SKILL.md")
    try:
        base = metadata_value(own_md, "base")
        need_raw = metadata_value(own_md, "base_min_version")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"stop: cannot read this skill's SKILL.md ({exc}); {REINSTALL}")
        return 1
    need = parse(need_raw)
    if not SKILL_NAME.fullmatch(base or ""):
        print(f"stop: this skill's metadata.base is {base!r}, not a skill name; {REINSTALL}")
        return 1
    if need is None:
        print(f"stop: this skill's metadata.base_min_version is {need_raw!r}, not MAJOR.MINOR.PATCH; {REINSTALL}")
        return 1
    base_md = os.path.join(skills_dir, base, "SKILL.md")
    fix = (f"run `bluebox skills refresh`, or `npx skills update` if npx installed it, "
           f"to put {base} {need_raw} or later into {skills_dir}, then ask again")
    fix_missing = (f"run `bluebox skills refresh`, or `npx skills add bluebox-hq/skills` if npx installed this skill, "
                   f"to put {base} {need_raw} or later into {skills_dir}, then ask again")
    no_way = "running that copy instead is no way around this, it is the older rules"
    if not os.path.isfile(base_md):
        print(f"stop: {base} is not installed beside this skill; {fix_missing}")
        return 1
    # The skills dir is trusted as it resolves (a dotfiles symlink is fine). The variant reads and runs
    # files from the base (SKILL.md, references/, scripts/), so every entry of it must resolve inside.
    root = os.path.realpath(skills_dir)
    try:
        escape = first_escape(os.path.join(skills_dir, base), root)
    except OSError as exc:
        print(f"stop: cannot read {os.path.join(skills_dir, base)} ({exc}); {fix}; {no_way}")
        return 1
    if escape:
        path, real = escape
        print(f"stop: {path} resolves outside {root}, to {real}; reinstall {base} {need_raw} or later "
              f"as a real directory in {skills_dir}, then ask again")
        return 1
    real_md = os.path.realpath(base_md)
    try:
        have_raw = metadata_value(real_md, "version")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"stop: cannot read {base_md} ({exc}); {fix}; {no_way}")
        return 1
    have = parse(have_raw)
    if have is None:
        print(f"stop: {base_md} has no MAJOR.MINOR.PATCH metadata.version (got {have_raw!r}); {fix}; {no_way}")
        return 1
    if have < need:
        print(f"stop: {base} {have_raw} is installed beside this skill, which needs {need_raw} or later; {fix}; {no_way}")
        return 1
    print(f"ok: {base} {have_raw} at {os.path.dirname(real_md)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
