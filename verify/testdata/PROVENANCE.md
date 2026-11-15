# Where the good fixtures come from

The three checkpoints in `good/` are measured, not hand-computed. They
were made on 2026-11-15 by running the archive's own functions from
`apps/door/src/merkle.ts` in monumental-archive/monumental-archive at
`910ba3b` (private; read-only, run from a scratch copy, nothing copied
here). The copy changed one import specifier (`./hash.js` to
`./hash.ts`) so Node 24's `--experimental-strip-types` could load it;
no function body changed.

For each checkpoint, `merkle_root` is `merkleRoot` over the SHA-256 of
the leaf strings below, `head` is `headHash` over
`{prevHead, merkleRoot, actCount, lastActId}`, `prev_head` is the
previous checkpoint's `head`, and the file is written the way the
archive's checkpoint job writes it: `JSON.stringify(record, null, 2)`
plus a newline, named by `seq` zero-padded to eight digits.

| File | Leaves | `act_count` | `last_act_id` |
| --- | --- | --- | --- |
| `00000000.json` | `a0`, `a1`, `a2` | 3 | `0193a6f4-1c2d-7e3f-8a4b-5c6d7e8f9a00` |
| `00000001.json` | `b0` | 1 | `0193a6f5-0000-7000-9000-000000000001` |
| `00000002.json` | `c0` to `c4` | 5 | `0193a6f6-ffff-7fff-bfff-ffffffffffff` |

The verifier is written from the README's description of the head,
not from that code. `test_vectors_reproduce` is the proof that the two
agree byte for byte: each `head` above recomputes from the README's
canonical record.
