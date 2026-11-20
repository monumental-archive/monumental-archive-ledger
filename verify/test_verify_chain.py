#!/usr/bin/env python3
"""Table tests for verify_chain.py (#27).

The three checkpoints in testdata/good/ are measured vectors, not
hand-computed ones: testdata/PROVENANCE.md says how each was made by
running the archive's own `headHash`. The verifier is written from the
README's description, so `test_vectors_reproduce` is the proof that the
description and the archive agree byte for byte.

Each red case changes one thing in a throwaway git repository and
asserts the exact message, not merely the exit status: a case scored on
exit alone can pass for the wrong reason.

stdlib `unittest`, the belt's one test idiom.
"""

import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import override
from unittest import mock

import verify_chain as vc

GOOD = Path(__file__).parent / "testdata" / "good"
HEADS = (
    "787eac210ef9f7e4280da47f635b5bf3a7eb3be7285ef0dc8330e1dfae2bf761",
    "76c4fe1b5dee2af384d2e25c760024d719f2c18b56ead995939344acd9b1219b",
    "dc8311742732510ac75d29789fb75f5166bac4d038cf1c44b96d4c9803f4ed76",
)
# The throwaway repositories must not read the runner's or a
# developer's git configuration: commit signing or hooks there would
# make a case fail for a reason that is not the chain's.
GIT_ENV = {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "verify-chain test",
    "GIT_AUTHOR_EMAIL": "test@invalid",
    "GIT_COMMITTER_NAME": "verify-chain test",
    "GIT_COMMITTER_EMAIL": "test@invalid",
}


def load(seq: int) -> dict[str, object]:
    """Load one good checkpoint.

    Returns:
        Good checkpoint `seq` as a dict.

    Raises:
        TypeError: the fixture is not a JSON object.

    """
    value: object = json.loads((GOOD / f"{seq:08d}.json").read_text(encoding="utf-8"))
    if not vc.is_object(value):
        msg = f"good checkpoint {seq} is not a JSON object"
        raise TypeError(msg)
    return value


def write(repo: Path, record: dict[str, object], name: str | None = None) -> None:
    """Write a record the way the archive does: 2-space JSON plus newline."""
    name = name or f"{record['seq']:08d}.json"
    text = json.dumps(record, indent=2) + "\n"
    (repo / "checkpoints" / name).write_text(text, encoding="utf-8")


def git_in(repo: Path, *args: str) -> None:
    """Run git in a throwaway repository, never the one running the tests.

    A pre-push hook exports GIT_DIR and its siblings, and they override
    `git -C`: without stripping them, `git init` here re-initialised the
    PUSHING repository and set its `core.bare` to true (measured on the
    first hooked push of this suite).
    """
    subprocess.run(
        ["git", "-C", str(repo), *args],  # ruff: ignore[start-process-with-partial-path]
        check=True,
        capture_output=True,
        env=vc.git_env(),
    )


class ChainCase(unittest.TestCase):
    """Each case runs in a fresh git repository with origin/main set."""

    @override
    def setUp(self) -> None:
        """Make an empty anchor repository whose main is origin/main."""
        self.enterContext(mock.patch.dict(os.environ, GIT_ENV))
        self.repo = Path(tempfile.mkdtemp(prefix="verify-chain-"))
        self.addCleanup(shutil.rmtree, self.repo)
        self.git("init", "-q", "-b", "main")
        (self.repo / "checkpoints").mkdir()
        (self.repo / "checkpoints" / ".gitkeep").write_text("", encoding="utf-8")
        self.commit("genesis")

    def git(self, *args: str) -> None:
        """Run git in the throwaway repository."""
        git_in(self.repo, *args)

    def commit(self, message: str) -> None:
        """Commit everything and point origin/main at the result."""
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", message)
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")

    def publish(self, *seqs: int) -> None:
        """Publish good checkpoints one commit each, as the archive does."""
        for seq in seqs:
            write(self.repo, load(seq))
            self.commit(f"checkpoint {seq}")

    def branch(self) -> None:
        """Start a pull request's branch off origin/main."""
        self.git("checkout", "-q", "-b", "change")

    def run_verifier(self) -> tuple[int, str, str]:
        """Run the verifier on the throwaway repository.

        Returns:
            The exit status, stdout and stderr.

        """
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            status = vc.main(["--repo", str(self.repo)])
        return status, out.getvalue(), err.getvalue()

    def assert_red(self, message: str) -> None:
        """Assert the verifier fails with exactly this message."""
        status, out, err = self.run_verifier()
        self.assertEqual((status, out, err), (1, "", f"verify-chain: {message}\n"))


class Vectors(unittest.TestCase):
    """The README's canonical record reproduces the archive's headHash."""

    def test_vectors_reproduce(self) -> None:
        """Each measured head recomputes from the README's description."""
        for seq, head in enumerate(HEADS):
            record = load(seq)
            self.assertEqual(record["head"], head)
            self.assertEqual(vc.canonical_head(record), head)


class Green(ChainCase):
    """Chains that verify."""

    def test_empty(self) -> None:
        """No checkpoints yet: passes and says so."""
        self.commit("adopt the verifier")
        status, out, err = self.run_verifier()
        self.assertEqual(
            (status, out, err),
            (0, "verify-chain: 0 checkpoints, append-only against HEAD~1\n", ""),
        )

    def test_good_chain_of_three(self) -> None:
        """Three checkpoints, each published as its own commit."""
        self.publish(0, 1, 2)
        status, out, err = self.run_verifier()
        self.assertEqual(
            (status, out, err),
            (
                0,
                (
                    f"verify-chain: 3 checkpoint(s) verified, head {HEADS[2]}, "
                    "append-only against HEAD~1\n"
                ),
                "",
            ),
        )

    def test_ignores_the_callers_repository(self) -> None:
        """Run as from a hook: GIT_DIR names another repository.

        The verifier must still judge `--repo`, and must leave the other
        repository exactly as it was.
        """
        self.publish(0, 1, 2)
        other = Path(tempfile.mkdtemp(prefix="verify-chain-caller-"))
        self.addCleanup(shutil.rmtree, other)
        git_in(other, "init", "-q", "-b", "main")
        config = (other / ".git" / "config").read_text(encoding="utf-8")
        os.environ["GIT_DIR"] = str(other / ".git")
        os.environ["GIT_WORK_TREE"] = str(other)
        status, out, err = self.run_verifier()
        self.assertEqual(
            (status, out, err),
            (
                0,
                (
                    f"verify-chain: 3 checkpoint(s) verified, head {HEADS[2]}, "
                    "append-only against HEAD~1\n"
                ),
                "",
            ),
        )
        self.assertEqual(
            (other / ".git" / "config").read_text(encoding="utf-8"),
            config,
        )

    def test_appending_on_a_branch(self) -> None:
        """A pull request that adds the next checkpoint is green."""
        self.publish(0, 1)
        self.branch()
        write(self.repo, load(2))
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "checkpoint 2")
        status, out, err = self.run_verifier()
        self.assertEqual(
            (status, out, err),
            (
                0,
                (
                    f"verify-chain: 3 checkpoint(s) verified, head {HEADS[2]}, "
                    "append-only against merge-base with origin/main\n"
                ),
                "",
            ),
        )


class Red(ChainCase):
    """Each case breaks exactly one property."""

    def test_wrong_head(self) -> None:
        """A head that is well-formed but not the record's hash."""
        self.publish(0, 1)
        record = load(2)
        record["head"] = "0" * 64
        write(self.repo, record)
        self.assert_red(
            f"checkpoints/00000002.json: head does not recompute (expected {HEADS[2]})",
        )

    def test_prev_head_does_not_chain(self) -> None:
        """A prev_head that is not the previous checkpoint's head."""
        self.publish(0, 1)
        record = load(2)
        record["prev_head"] = HEADS[0]
        record["head"] = vc.canonical_head(record)
        write(self.repo, record)
        self.assert_red(
            "checkpoints/00000002.json: prev_head does not chain to seq 1's head",
        )

    def test_gap_in_seq(self) -> None:
        """Seq 0 then seq 2, with seq 1 never published."""
        self.publish(0)
        write(self.repo, load(2))
        self.assert_red("checkpoints/00000002.json: seq gap, expected seq 1 next")

    def test_extra_field(self) -> None:
        """A record with a field the README does not define."""
        record = load(0)
        record["note"] = "hello"
        write(self.repo, record)
        self.assert_red("checkpoints/00000000.json: unexpected field 'note'")

    def test_changed_earlier_checkpoint(self) -> None:
        """A consistent rewrite of history: every head re-derived."""
        self.publish(0, 1, 2)
        self.branch()
        prev = None
        for seq in range(3):
            record = load(seq)
            if seq == 0:
                record["act_count"] = 4
            record["prev_head"] = prev
            record["head"] = vc.canonical_head(record)
            prev = record["head"]
            write(self.repo, record)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "rewrite")
        self.assert_red(
            "checkpoints/00000000.json: modified - checkpoints only ever append",
        )

    def test_deleted_checkpoint(self) -> None:
        """Dropping the newest checkpoint leaves a valid but shorter chain."""
        self.publish(0, 1, 2)
        self.branch()
        self.git("rm", "-q", "checkpoints/00000002.json")
        self.git("commit", "-q", "-m", "drop")
        self.assert_red(
            "checkpoints/00000002.json: deleted - checkpoints only ever append",
        )


if __name__ == "__main__":
    unittest.main()
