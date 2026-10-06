# Architecture

Phase 0 implements configuration -> public asset catalog -> bounded cache download
-> PyArrow Feather read -> Polars normalization/validation -> Typer CLI.

Pydantic validates configuration; receipts capture source provenance. Tests generate
tiny synthetic Feather payloads in temporary directories and require no network.
CI runs Python 3.11 and 3.12 on Windows and Linux. Full live data is excluded from CI.

Phase 1 uses a directed python-igraph graph. IDs stay UInt64 in Polars, map to dense
indices for igraph, and serialize as strings in JSON. Vertices and edges are sorted
before construction; weights align with the sorted edge table. Dense NumPy buffers
avoid allocating a Python dictionary for each of the millions of edges.

Minimum-hop queries use unweighted outward shortest paths; normalized-strength
queries use nonnegative weights and igraph's automatic shortest-path algorithm
(Dijkstra for these weights). See the [igraph API](https://igraph.org/python/versions/latest/api/igraph.Graph.html).
Equal-cost paths are not promised unique or identical across igraph versions;
the manifest records the installed igraph version. Every result validates directed
edge ordering, totals, threshold, cost formula and endpoint/exclusion consistency
with Pydantic before writing. Output destinations are not overwritten.

The session loads/validates sources once for a two-mode demo. Exclusion constructs
a fresh graph and leaves cached edges and original input totals unchanged. No
processed graph cache is introduced without evidence of a startup bottleneck.
An observed full-cache `demo build` run took approximately 3.8 seconds on this
machine; this is a single warm-local-file measurement, not a performance guarantee.

Phase 2 adds a public v888 full-SWC provider, explicit units, forest validation,
one common coordinate transform and versioned `skeleton_scene` bundles. A generic
SWC parser supports nm/µm, but the default provider uses the verified nm export
under `compiled_data/banc_888/banc_banc_space_swc/`. The legacy root-level source
is not used because its IDs/units differ. This corrects the initial catalog brief
using actual object/coordinate checks; details are in [morphology.md](morphology.md).

Scene export has a 20 MB per-object limit and 100 MB aggregate source budget.
It validates all files in a temporary sibling directory, then publishes the bundle
to a new destination. File-based loading works without source caches or network.
A dependency-free HTML inspection aid verifies morphology ahead of Godot work;
it is not a second application architecture or a substitute for the planned viewer.

Phase 3 is an offline Godot 4 viewer. A bounded GDScript loader verifies all bundle
hashes and validates directed paths, costs, exact string IDs, coordinates and
forest topology before replacing the active scene. One ArrayMesh per neuron
batches all segments; isolated roots use point geometry. Godot uses the existing
world coordinates directly. An orthographic orbit camera, screen-space picking,
metadata/edge panel and timed illustrative highlighting form the static MVP.
See [viewer setup and verification](godot.md). Python retains scientific computation;
Godot owns display/control. Later detail phases build on this contract.

Phase 4 adds an optional FastAPI/Uvicorn adapter on loopback. Metadata is loaded
and verified at startup; a single background worker loads/reuses one igraph session
for the requested threshold and exports existing scene contracts. Source/target
search and status polling remain responsive to separate HTTP requests. No graph
logic moves into GDScript. The viewer's Explore panel searches static metadata,
selects exact string IDs, submits a bounded job, then invokes the existing bundle
loader and switches between mode results. Input changes invalidate stale results;
failed queries retain the previous display. See [local API](local-api.md).

Windows export staging now uses a UUID-named sibling created with ordinary mkdir.
TemporaryDirectory's owner-only Windows ACL made renamed bundles unreadable by
the desktop user when built by a sandbox account. Inheriting the output parent's
permissions fixes the cross-process workflow while preserving validate-before-rename
publication and cleanup on failure.

No global installation, hosted service or optional live-data dependency is needed.
The workspace's `.tools` uv installation and `.venv` are ignored local tooling.

Phase 5 adds a narrowly scoped public legacy-mesh reader for two BANC neuropil
outlines, without new dependencies. These unversioned assets keep separate source
receipts and share the path coordinate transform. Scene schema 2 carries optional
context geometry; schema 1 outputs/readers remain supported. Godot renders two
batched translucent surfaces with independent context/path camera fitting. See
[context.md](context.md) for provenance, format and limits.

Phase 6A adds a narrow `EmProvider` interface and public aligned-v0 implementation.
An exact selected SWC node resolves into source nm coordinates; bounded HTTP ranges
retrieve only precomputed shard indices and JPEG chunks. No graph calculation moves
into the viewer. Optional Pillow exports a hash-checked portable XY PNG stack with
per-range source provenance, separate from the v888 skeleton/graph scene contract.
Godot's EM tab uses the shared localhost job worker or opens a saved stack offline.
It labels the point as morphology context; version-consistent synapse evidence
remains pending because the examined v3 table's row groups do not prune efficiently.
See [em.md](em.md) for the measured limitation and coordinate/access contracts.

Phase 7 adds a graph intervention contract and comparison report shared by CLI and
API. A temporary filtered graph preserves the base graph's vertex universe and raw
input totals; isolated metadata-less vertices are retained unless explicitly filtered.
The API resolves baselines from its own completed path jobs, validates their scene
hashes, and rejects changed source hashes. No-path outcomes retain a query manifest.
Morphology failure does not erase a valid graph comparison. Godot pins an explicit
baseline and switches independently validated before/after scenes. Rules, source
versions and objectives stay in Python; see [interventions.md](interventions.md).

## Optional selected-edge evidence

`synapses/transport.py` implements a fixed-host, bounded JSON CAVE reader using
standard local credentials. `synapses/evidence.py` pins v888, verifies the detector
and response units, queries one directed pair, and exports a validated subset with
the source graph. There is no automatic query from graph or API startup. Saved
bundles validate offline. `em synapse` resolves an exact returned ID to the same
EM provider; schema-2 manifests carry its independent evidence provenance. Godot
opens either EM schema and keeps each image labeled with its own point identity.
Live CAVE verification is pending local setup; see `synapses.md`.
