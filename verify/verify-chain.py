#!/usr/bin/env python3
"""Verify the published checkpoint chain, as the README says anyone can.

Reads every file in `checkpoints/` and fails by name unless each one is
a well-formed record, the files run seq 0, 1, 2 ... under their
zero-padded names, every `prev_head` is the previous `head`, and every
`head` is the SHA-256 of the canonical record the README describes.
Then checks that history here only appends: against the merge base
with origin/main (on main itself, the previous commit), no existing
checkpoint file was modified, renamed or deleted.

What it cannot check is the Merkle root: that needs the acts, which
never enter this repository by design.

Standard library only, so a stranger needs nothing but Python and git:

    python3 verify/verify-chain.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess  # ruff: ignore[suspicious-subprocess-import]
import sys
from pathlib import Path

PROG = "verify-chain"
FIELDS = (
    "v",
    "seq",
    "prev_head",
    "merkle_root",
    "act_count",
    "last_act_id",
    "head",
)
NAME = re.compile(r"\A(\d{8})\.json\Z")
HEX64 = re.compile(r"\A[0-9a-f]{64}\Z")
UUID7 = re.compile(
    r"\A[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z",
)
DEFAULT_BRANCH = "origin/main"
# Tracked beside the checkpoints so git keeps the empty directory.
IGNORED = frozenset({".gitkeep"})
CHANGES = {"M": "modified", "D": "deleted", "T": "changed type"}


class ChainError(Exception):
    """One named reason the chain does not verify."""


def canonical_head(record: dict[str, object]) -> str:
    """Compute the head the README defines for a record.

    The SHA-256 of the compact JSON object
    {"v":1,"prev_head":…,"merkle_root":…,"act_count":…,"last_act_id":…},
    keys in that order, no whitespace.

    Returns:
        The head as 64 lower-case hex characters.

    """
    canonical = {
        "v": record["v"],
        "prev_head": record["prev_head"],
        "merkle_root": record["merkle_root"],
        "act_count": record["act_count"],
        "last_act_id": record["last_act_id"],
    }
    text = json.dumps(canonical, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode()).hexdigest()


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_hex64(value: object) -> bool:
    return isinstance(value, str) and HEX64.match(value) is not None


def _shape_problem(record: dict[str, object]) -> str | None:
    """Name the first way the record departs from the README's shape.

    Returns:
        The problem, or None when the record has the README's shape.

    """
    extra = [k for k in record if k not in FIELDS]
    missing = [k for k in FIELDS if k not in record]
    checks = (
        (bool(extra), f"unexpected field {extra[0]!r}" if extra else ""),
        (bool(missing), f"missing field {missing[0]!r}" if missing else ""),
    )
    for failed, problem in checks:
        if failed:
            return problem
    prev = record["prev_head"]
    last = record["last_act_id"]
    count = record["act_count"]
    checks = (
        (
            record["v"] != 1 or not _is_int(record["v"]),
            f"v is {record['v']!r}, expected 1",
        ),
        (
            not _is_int(record["seq"]) or record["seq"] < 0,
            "seq is not a non-negative integer",
        ),
        (
            not _is_hex64(record["merkle_root"]),
            "merkle_root is not 64 lower-case hex characters",
        ),
        (not _is_hex64(record["head"]), "head is not 64 lower-case hex characters"),
        (
            prev is not None and not _is_hex64(prev),
            "prev_head is neither null nor 64 lower-case hex characters",
        ),
        (
            not _is_int(count) or count < 1,
            "act_count is not a positive integer",
        ),
        (
            not isinstance(last, str) or UUID7.match(last) is None,
            "last_act_id is not a lower-case UUIDv7",
        ),
    )
    for failed, problem in checks:
        if failed:
            return problem
    return None


def read_record(directory: Path, name: str, expected_seq: int) -> dict[str, object]:
    """Read one checkpoint file and check its name and shape.

    Returns:
        The record.

    Raises:
        ChainError: the name, the JSON or the shape is wrong.

    """
    label = f"{directory.name}/{name}"
    match = NAME.match(name)
    if not match:
        msg = f"{label}: not a checkpoint name (8-digit seq + .json)"
        raise ChainError(msg)
    if int(match.group(1)) != expected_seq:
        msg = f"{label}: seq gap, expected seq {expected_seq} next"
        raise ChainError(msg)
    try:
        record = json.loads((directory / name).read_text(encoding="utf-8"))
    except json.JSONDecodeError as err:
        msg = f"{label}: not valid JSON ({err.msg})"
        raise ChainError(msg) from err
    if not isinstance(record, dict):
        msg = f"{label}: not a JSON object"
        raise ChainError(msg)
    problem = _shape_problem(record)
    if problem is not None:
        msg = f"{label}: {problem}"
        raise ChainError(msg)
    if record["seq"] != expected_seq:
        msg = f"{label}: seq is {record['seq']}, the name says {expected_seq}"
        raise ChainError(msg)
    return record


def verify_files(directory: Path) -> list[dict[str, object]]:
    """Verify every checkpoint in `directory`.

    Returns:
        The chain, in seq order.

    Raises:
        ChainError: the first checkpoint that does not verify, by name.

    """
    if not directory.is_dir():
        msg = f"{directory}: no such directory"
        raise ChainError(msg)
    names = sorted(p.name for p in directory.iterdir() if p.name not in IGNORED)
    chain: list[dict[str, object]] = []
    for seq, name in enumerate(names):
        label = f"{directory.name}/{name}"
        record = read_record(directory, name, seq)
        expected_prev = chain[-1]["head"] if chain else None
        if record["prev_head"] != expected_prev:
            if seq == 0:
                msg = f"{label}: prev_head must be null at seq 0"
            else:
                msg = f"{label}: prev_head does not chain to seq {seq - 1}'s head"
            raise ChainError(msg)
        expected_head = canonical_head(record)
        if record["head"] != expected_head:
            msg = f"{label}: head does not recompute (expected {expected_head})"
            raise ChainError(msg)
        chain.append(record)
    return chain


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    # ruff: ignore[subprocess-without-shell-equals-true]
    return subprocess.run(
        ["git", "-C", str(repo), *args],  # ruff: ignore[start-process-with-partial-path]
        capture_output=True,
        text=True,
        check=False,
    )


def _rev(repo: Path, ref: str) -> str | None:
    result = _git(repo, "rev-parse", "--verify", "-q", f"{ref}^{{commit}}")
    return result.stdout.strip() if result.returncode == 0 else None


def resolve_base(repo: Path, explicit: str | None) -> tuple[str | None, str]:
    """Choose the commit the append-only check compares with.

    Returns:
        The base commit (None on a first commit) and how it was chosen.

    Raises:
        ChainError: no base can be derived.

    """
    if explicit is not None:
        base = _rev(repo, explicit)
        if base is None:
            msg = f"--base {explicit} does not name a commit"
            raise ChainError(msg)
        return base, explicit
    head = _rev(repo, "HEAD")
    if head is None:
        msg = "not inside a git work tree with a commit"
        raise ChainError(msg)
    default = _rev(repo, DEFAULT_BRANCH)
    if default is None:
        msg = f"no {DEFAULT_BRANCH} to compare with; pass --base REF"
        raise ChainError(msg)
    if head == default:
        return _rev(repo, "HEAD~1"), "HEAD~1"
    result = _git(repo, "merge-base", "HEAD", DEFAULT_BRANCH)
    if result.returncode != 0:
        msg = f"HEAD shares no history with {DEFAULT_BRANCH}"
        raise ChainError(msg)
    return result.stdout.strip(), f"merge-base with {DEFAULT_BRANCH}"


def verify_append_only(repo: Path, directory: str, base: str) -> None:
    """Check that no checkpoint present at `base` changed in the work tree.

    Raises:
        ChainError: a checkpoint was modified, renamed or deleted.

    """
    result = _git(repo, "diff", "--no-renames", "--name-status", base, "--", directory)
    if result.returncode != 0:
        msg = f"git diff against the base failed: {result.stderr.strip()}"
        raise ChainError(msg)
    for line in result.stdout.splitlines():
        status, _, path = line.partition("\t")
        if Path(path).name not in IGNORED and status in CHANGES:
            msg = f"{path}: {CHANGES[status]} - checkpoints only ever append"
            raise ChainError(msg)


def main(argv: list[str] | None = None) -> int:
    """Run the verifier and report one line.

    Returns:
        0 on a verified chain, 1 with a named reason on stderr.

    """
    parser = argparse.ArgumentParser(prog=PROG, description=__doc__.splitlines()[0])
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path(),
        help="the clone to verify (default: the current directory)",
    )
    parser.add_argument(
        "--base",
        help="compare against this commit instead of the derived base",
    )
    args = parser.parse_args(argv)
    try:
        line = verify(args.repo, args.base)
    except ChainError as err:
        print(f"{PROG}: {err}", file=sys.stderr)
        return 1
    print(f"{PROG}: {line}")
    return 0


def verify(repo: Path, explicit_base: str | None) -> str:
    """Verify the files, then that they only appended.

    Returns:
        The one-line summary of a verified chain.

    """
    chain = verify_files(repo / "checkpoints")
    base, how = resolve_base(repo, explicit_base)
    if base is None:
        how = "nothing (the first commit)"
    else:
        verify_append_only(repo, "checkpoints", base)
    if not chain:
        return f"0 checkpoints, append-only against {how}"
    return (
        f"{len(chain)} checkpoint(s) verified, head {chain[-1]['head']}, "
        f"append-only against {how}"
    )


if __name__ == "__main__":
    sys.exit(main())
