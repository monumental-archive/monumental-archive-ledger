# Monumental Archive — ledger checkpoint chain

<!-- badges:begin -->
[![ci](https://github.com/monumental-archive/monumental-archive-ledger/actions/workflows/ci.yml/badge.svg)](https://github.com/monumental-archive/monumental-archive-ledger/actions/workflows/ci.yml)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/monumental-archive/monumental-archive-ledger/badge)](https://scorecard.dev/viewer/?uri=github.com/monumental-archive/monumental-archive-ledger)
[![SLSA source](https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2Fmonumental-archive%2Fmonumental-archive-ledger%2Flevels%2Fmonumental-archive-ledger%2Fsource.shield.json)](https://raw.githubusercontent.com/monumental-archive/monumental-archive-ledger/levels/monumental-archive-ledger/source.report.json)
[![OpenSSF Best Practices](https://www.bestpractices.dev/projects/16736/badge)](https://www.bestpractices.dev/projects/16736)
[![OpenSSF Baseline](https://www.bestpractices.dev/projects/16736/baseline)](https://www.bestpractices.dev/projects/16736)
[![REUSE status](https://api.reuse.software/badge/github.com/monumental-archive/monumental-archive-ledger)](https://api.reuse.software/info/github.com/monumental-archive/monumental-archive-ledger)
[![license](https://img.shields.io/badge/license-CC0--1.0-blue)](LICENSES/)
[![fair-software](https://img.shields.io/badge/fair--software.eu-%E2%97%8F%20%E2%97%8F%20%E2%97%8B%20%E2%97%8B%20%E2%97%8F-orange)](https://fair-software.eu)
<!-- badges:end -->

This repository is the **public anchor** for the Monumental Archive's
acts ledger (ADR 0022 §one-checkpoint-chain). It contains no archive
content — only cryptographic checkpoints: hashes of hashes.

## What a checkpoint is

Each file in [`checkpoints/`](checkpoints/) is one sealed period of the
archive's append-only ledger, named by its `seq` zero-padded to eight
digits (`00000000.json`, `00000001.json`, …):

```json
{
  "v": 1,
  "seq": 0,
  "prev_head": null,
  "merkle_root": "<hex sha-256>",
  "act_count": 123,
  "last_act_id": "<uuidv7>",
  "head": "<hex sha-256>"
}
```

- `merkle_root` — root of an RFC-6962-style Merkle tree whose leaves are
  the period's act content hashes (each act hash covers the act's
  envelope plus a **salted** hash of its payload — no payload, and no
  guessable payload fingerprint, ever enters this repository).
- `head` — SHA-256 of the canonical JSON record
  `{"v":1,"prev_head":…,"merkle_root":…,"act_count":…,"last_act_id":…}`,
  chaining every checkpoint to the one before it.
- One checkpoint = **one git commit**, so this repository's own commit
  DAG is a second tamper-evidence layer: rewriting an old checkpoint
  changes every later commit hash, and every clone in the world notices.

## Why it exists

The archive's ledger records every act performed on the archive. This
chain makes that history **externally witnessed**: the archive's
operators cannot silently rewrite or backdate it, because the sealed
heads live here, in public, in every clone. Erased records (GDPR
Article 17 and the archive's removal ladder) keep their sealed hashes —
the chain verifies end-to-end across an erasure, proving an act existed
and when, while its destroyed payload stays unrecoverable.

## Verifying

Anyone with read access to the archive database can re-derive the whole
chain from ledger zero. The archive re-derives its database chain before
it publishes, and refuses to publish a checkpoint that does not
re-derive. This repository checks the published files.

Third parties without database access verify the weaker but still
meaningful properties: the head chain is internally consistent, and
history here only ever appends. From any clone, with Python 3 and git:

```bash
python3 verify/verify_chain.py
```

It fails by name unless every checkpoint has exactly the seven fields
above, `seq` runs 0, 1, 2 … under its file name, each `prev_head` is
the previous checkpoint's `head` (`null` at `seq` 0), each `head`
recomputes, and no checkpoint that existed at the merge base with
`origin/main` (on `main` itself, the previous commit) has been
modified, renamed or deleted. This repository's gate runs the same
command and the verifier's own tests as its `test` task.

Known gap: nothing compares the two. The archive verifies its database
and this repository verifies its files; no automated check diffs one
against the other. Nor is the Merkle root checked here: it needs the
acts, which never enter this repository by design.

Clones welcome — a copy of this repository IS the verification
infrastructure.
