# Selected synapse evidence (Phase 6B)

The optional CLI can query **one directed edge** from a validated graph path in
CAVE materialization **888**, save a small evidence bundle, then export an EM
slice stack around a returned predicted-synapse center. Godot's EM tab opens that
stack with its detector, synapse ID and pre/post IDs. Core pathfinding and the
existing morphology-point EM workflow still work without credentials.

**Implementation status:** the complete file workflow is tested with synthetic
responses, including the real Godot loader/panel. A live authenticated BANC query
has **not** been verified on this workstation: no supported local token was found
on 2026-10-06. The availability of `synapses_v3` in v888 and its deployed schema
will be checked on the first authenticated request. Full Phase 6 remains pending
that check and inspection of real, version-consistent synapse positions.

## Configure an existing BANC account locally

An account needs permission to read the BANC `brain_and_nerve_cord` datastack.
Follow the official [BANC account instructions](https://github.com/jasper-tms/the-BANC-fly-connectome)
and [CAVE authentication documentation](https://www.caveconnecto.me/CAVEclient/api/auth/)
to obtain your existing token. Do not put tokens in chat, CLI arguments, source,
generated bundles or this repository. The following helper prompts with hidden
input and writes the standard host-specific credential file outside Git:

```powershell
.\.venv\Scripts\python.exe scripts/configure_cave.py
```

It refuses to overwrite an existing file. The provider reads, in order:

1. `BANC_CAVE_TOKEN` from the process environment, if explicitly set;
2. `~/.cloudvolume/secrets/cave.fanc-fly.com-cave-secret.json`;
3. `~/.cloudvolume/secrets/cave-secret.json`.

Credential JSON accepts `brain_and_nerve_cord` or the standard `token` key.
It never copies or prints credential values. An absent/invalid token produces an
actionable error before any network request. The core application does not import
an SDK or acquire a token automatically; this narrow provider uses standard-library
HTTPS against the official materialization API, with explicit body-size limits.

## Query, inspect and open

Use a graph path produced by `path find` or `demo build`. For this workspace:

```powershell
uv run banc-explorer synapses fetch --path generated/phase1-demo/normalized.json --edge-index 0 --limit 250 --output generated/evidence/first-edge
uv run banc-explorer synapses validate --evidence generated/evidence/first-edge
```

Indices start at zero. The path supplies the exact pre/post IDs, connectivity
version and static graph count; these cannot be replaced by guessed identifiers.
Choose an exact `rows[].id` from the saved `evidence.json`:

```powershell
uv sync --locked --extra api --extra em
$synapseId = (Get-Content generated/evidence/first-edge/evidence.json -Raw | ConvertFrom-Json).rows[0].id
uv run banc-explorer em synapse --evidence generated/evidence/first-edge --synapse-id $synapseId --output generated/em-synapse
```

An empty result has no selectable synapse. Read the count comparison before using
it; this command does not fabricate a point when a query is empty. `em synapse`
supports the existing `--size-xy`, `--depth`, `--mip`, `--config` and `--offline`
options and the same 32 MB maximum EM transfer budget. The default remains
256 × 256 × 32 voxels. Saved evidence and EM slices reopen without CAVE credentials.

In Godot, choose **EM → Open stack… → generated/em-synapse/roi.json**. The image
label distinguishes a predicted synapse from a morphology node. The ordinary
**Inspect point** action continues to use the selected SWC node. This milestone
does not yet add CAVE queries to the localhost API or a 3D synapse marker layer.

## Bounds and provenance

- Fixed HTTPS host `cave.fanc-fly.com`; redirects are rejected, including login
  redirects. Authorization is never forwarded to another host. HTTP errors are
  sanitized without printing response bodies or credentials.
- Four requests maximum: v888 metadata, its table list, detector-table metadata,
  and one filtered query. Three metadata bodies are capped at 100 KB each and the
  query at 2 MB: **2.3 MB maximum response payload per operation**. Compressed or
  oversized responses are refused. There is no bulk table fallback or pagination.
- `synapses_v3` for v3 paths, `synapses_v2` for v2 paths, only if present in v888.
  Both `pre_pt_root_id` and `post_pt_root_id` are equality-filtered on the server.
  The detector size cutoff is 10 for v3, 5 for v2; returned rows are checked again.
- Default 250 rows, maximum 1,000. One extra sentinel row detects the request cap.
  Any cap or server warning labels the count comparison `incomplete`. Uncapped
  responses are labeled `matches` or `differs` against the static edge count;
  matching counts do **not** prove that contacts reproduce the static release.
- Native table resolution is recorded. The query explicitly requests `[1,1,1]`
  nm coordinates and requires the response `dataframe_resolution` header to
  confirm them. Missing/conflicting units are errors; values are never guessed
  from magnitude. The selected point is the returned `ctr_pt_position`, not a
  soma, SWC sample, or an inferred pre/post midpoint.
- `evidence.json` includes query/filter definitions, exact string IDs, response
  body hashes/sizes/URLs, materialization timestamp, detector, graph source/hash,
  count comparison and software version. `graph-path.json` is bundled and checked
  against its hash and the selected edge. The receipts hash bounded responses,
  not a multi-GB source object. No credential/user details are saved.
- EM contract version 2 records synapse/query/evidence/path provenance. Version 1
  remains the SWC-point contract. The image alignment is still independently
  labeled v0, with null image materialization; it is not relabeled v888.

These are predicted anatomical contacts and structural graph paths. EM context
does not independently validate a contact, prove transmission, or simulate firing.
CAVE table enrichment/validity filters may differ from the static archive even
when the materialization and detector labels agree. A mismatch is preserved.

## Why this uses a selective service

The public v3 enriched Parquet inspected for Phase 6A is 19,733,123,829 bytes;
all 1,989 row groups survive the demo pair's root-ID min/max filter. Projected
ID/pre/post/XYZ columns still require about 7.76 GB. The alternative slim v3
Parquet is 5,609,494,483 bytes with four enormous row groups and no column indexes.
Its 6,733-byte footer was inspected on 2026-10-06; no synapse data pages were read.

The public enriched-table prose describes a different schema/size and nm units,
while current footer coordinate ranges do not establish those units. We do not
infer a conversion from these discrepancies. The raw v3 documentation explicitly
describes 16 × 16 × 45 nm voxels, which must not be assumed for every other export.

Primary references: [BANC v3 raw-file documentation](https://storage.googleapis.com/lee-lab_brain-and-nerve-cord-fly-connectome/documentation/banc_888_synapses_v3_human_readable.md),
[v3 enriched documentation](https://storage.googleapis.com/lee-lab_brain-and-nerve-cord-fly-connectome/documentation/banc_888_synapses_v3_enriched.md),
[CAVE materialization client](https://www.caveconnecto.me/CAVEclient/api/materialize/),
[official query/response implementation](https://github.com/CAVEconnectome/MaterializationEngine/tree/master/materializationengine/blueprints/client).
