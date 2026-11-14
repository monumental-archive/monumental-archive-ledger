# Monumental Archive — ledger checkpoint chain

<!-- badges:begin -->
[![ci](https://github.com/monumental-archive/monumental-archive-ledger/actions/workflows/ci.yml/badge.svg)](https://github.com/monumental-archive/monumental-archive-ledger/actions/workflows/ci.yml)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/monumental-archive/monumental-archive-ledger/badge)](https://scorecard.dev/viewer/?uri=github.com/monumental-archive/monumental-archive-ledger)
<!-- pending (human step): OpenSSF Best Practices — answer the form from docs/best-practices.md, then set 'bestpractices <BP_ID>' in .badge-states and re-run fix:badges -->
<!-- pending (human step): REUSE — register at https://api.reuse.software/register (no account: name, email, project URL, confirmation link), then set 'reuse registered' in .badge-states and re-run fix:badges -->
[![license](https://img.shields.io/badge/license-CC0--1.0-blue)](LICENSES/)
[![fair-software](https://img.shields.io/badge/fair--software.eu-%E2%97%8F%20%E2%97%8F%20%E2%97%8B%20%E2%97%8B%20%E2%97%8B-orange)](https://fair-software.eu)
<!-- badges:end -->

This repository is the **public anchor** for the Monumental Archive's
acts ledger (ADR 0022 §one-checkpoint-chain). It contains no archive
content — only cryptographic checkpoints: hashes of hashes.

## What a checkpoint is

Each file in [`checkpoints/`](checkpoints/) is one sealed period of the
archive's append-only ledger:

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
chain from ledger zero and diff it against these files (the archive runs
exactly that check in CI, and refuses to publish a checkpoint that does
not re-derive). Third parties without database access verify the weaker
but still meaningful properties: the head chain is internally
consistent, and history here only ever appends.

Clones welcome — a copy of this repository IS the verification
infrastructure.
