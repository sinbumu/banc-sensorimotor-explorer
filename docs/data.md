# Data baseline and observed schema

Use BANC materialization 888, default connectivity v3; v2 has a separate cache
filename and is selectable through configuration. Do not mix live annotations.

Verified public HTTPS objects on 2026-10-02:

- https://storage.googleapis.com/lee-lab_brain-and-nerve-cord-fly-connectome/compiled_data/banc_888/banc_888_meta.feather
- https://storage.googleapis.com/lee-lab_brain-and-nerve-cord-fly-connectome/compiled_data/banc_888/banc_888_edgelist_simple_v3.feather

The catalog also supports `banc_888_edgelist_simple_v2.feather` at that prefix;
v2 was not downloaded or validated in this session.

Phase 2 additionally verifies selected full SWCs under
`compiled_data/banc_888/banc_banc_space_swc/<id>_skeleton.swc` (nm).
See [morphology.md](morphology.md) for corrected version/unit handling and receipts.

| Object | Bytes | Rows | Columns | GCS generation |
|---|---:|---:|---:|---|
| Metadata | 57,503,026 | 188,508 | 81 | 1787336614757441 |
| v3 edges | 359,161,658 | 13,620,865 | 6 | 1786578377086929 |

SHA-256:

```text
meta: 86ccf5df0c67419f8c5f43e93a7ed38d23a080e9f7fde26737290252f3780098
v3:   8c296e946f3c69a8c7222f30ad75fa8a98eeb189124fec6df829c9125f4be64b
```

The public files differ in row counts and sizes from the tutorial estimates.
Materialization identifies root IDs, but the public object names alone do not pin
every annotation/compiled-file revision. Preserve receipts and reports for each run;
the downloader does not promise to recover an old generation after upstream removal.
Hashes are local integrity records, not publisher-signed authenticity proofs.

Metadata IDs arrive as decimal strings; `proofread` arrives as `TRUE`/`FALSE`.
Normalize IDs directly to UInt64, rejecting floats, nulls, zero and duplicate IDs.
Normalize proofread flags explicitly; null means unknown and is excluded by the
proofread-only selector. Additional metadata columns/classes are retained.
Current data contains glia, trachea, unclassified rows and several intrinsic classes;
the expected class list in AGENTS.md is not an exhaustive schema enum.

Edges arrive as `pre`/`post` strings, integer `count`/`pre_count`/`post_count`, and
floating `norm`. Validate positive counts, finite norms in (0, 1], count <= totals,
and unique directed pairs. Retain original norm values. The observed maximum
absolute discrepancy from count/post_count is 0.00005, so validation allows
0.000051 for rounding. Path costs recompute count/post_count from the source totals.
Exports retain the rounded source value as `norm` and the recomputed ratio as
`normalized_input`; filtering does not renormalize the target's input total.

`count >= 5` retains 1,926,146 edges without changing the cached source.
Proofread candidate counts: 14,537 sensory, 805 motor.
The detector's per-synapse size cutoff is distinct from this edge-count threshold.

Downloads use standard-library HTTPS for these two known public objects. fsspec/gcsfs
can be added when remote selective access is needed; avoiding them here reduces
bootstrap dependencies without changing the public-static-data architecture.

The Phase 1 graph audit found 169,078 unique raw endpoint IDs, all represented in
metadata, and 19,430 metadata IDs with no raw edges. The graph retains isolated
metadata vertices and any hypothetical metadata-less endpoint IDs, with explicit
coverage counts in every result. Default graph: 188,508 vertices / 1,926,146 edges.
No proofreading, class or region filter is applied to intermediate neurons.

`tests/fixtures/banc_v888_v3_path_sample.json` contains only three actual metadata
rows and two path edges with source receipts. It is not an induced subgraph or
a certificate of global optimality; original totals include out-of-sample edges.
