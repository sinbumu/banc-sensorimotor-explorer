# Progress — 2026-10-02

Phases 0–4 implemented and verified on Windows Python 3.12 and Godot 4.7.2.

- Python package, uv lock, config/catalog, bounded download/cache receipts.
- Offline validation of hashes, metadata schema, exact IDs, proofread flags,
  edge counts/norms and duplicate directed pairs.
- Public metadata 188,508 rows; v3 edges 13,620,865 rows.
- Local report: `generated/data-validation.json` (not tracked).
- Unit tests and an offline Feather/CLI integration test; Windows/Linux CI defined.
- Verification: `uv run --offline banc-explorer data validate` succeeded;
  22 tests passed and `ruff check .` passed. Candidate sensory/motor commands
  succeeded against real metadata, including body-part filtering.
- The elevated uv test run emitted a Windows pytest cache-write warning;
  the normal workspace Python test run passed without that warning.
- No commit/push performed. No raw data or generated output staged.

Phase 1:

- Directed igraph, thresholding and neuron exclusion; all input totals preserved.
- Minimum-hop and normalized-strength objectives with exact count/post_count ratios.
- Pydantic graph path contract: versioned provenance, source hashes/generations,
  graph coverage, costs, exclusions and exact JSON string IDs.
- `path find` and `demo build` CLI commands; data-driven demo pair selection.
- All 169,078 raw edge endpoint IDs covered by metadata; 19,430 metadata isolates.
- Default filtered graph: 188,508 vertices, 1,926,146 edges.
- Real demo: source 720575941350568496 (SNta35), target 720575941463793552
  (accessory_tibia_flexor_C). Both modes choose IN03A009 as the intermediate neuron.
  Two hops, edge counts 11/10, normalized cost 11.0713078.
- Excluding intermediate 720575941557376164 yields a 3-hop normalized route
  through AN05B009 and IN03A007 (cost 14.6115986). Graph intervention only.
- Local results: `generated/phase1-demo/{selection,hops,normalized,excluded-normalized}.json`.
- Added tiny real-data fixture with provenance; synthetic tests cover differing
  objectives, direction, no path, isolates, zero costs, threshold/exclusion, metadata
  absence, ID precision, corrupted contracts and offline v2/v3 CLI round trips.
- 40 tests passed; Ruff passed. Live `demo build` and an excluded-neuron `path find`
  succeeded. No visual checks apply to this CLI milestone.
- Installed igraph/NumPy (roughly 16 MB compressed downloads), reusing existing
  `.cache/banc/v888/` data without any new BANC downloads. uv.lock updated.
- No commit/push performed.

Phase 2:

- Found an upstream unit/version discrepancy: legacy root-level SWC is µm for
  the checked sensory neuron; the selected motor's v888 ID returns 404 there.
- Verified and adopted `compiled_data/banc_888/banc_banc_space_swc/<id>_skeleton.swc`
  in nm. Updated AGENTS.md and source documentation; no older-ID fallback.
- Fetched three SWCs (4,084,517 bytes total) plus a 1,348-byte legacy diagnostic.
  Cache: `.cache/banc/v888/skeletons/`. No synapse/mesh/EM/full archive downloads.
- Parser handles forests, arbitrary row order, zero-based IDs, cycle/missing-parent
  detection and explicit source units. Forward/inverse world transforms tested.
- Exported `generated/scenes/phase2-demo/` with full provenance and checksums:
  three neurons, 60,659 points, 60,656 branches, no simplification.
- Added offline scene validation and self-contained inspection HTML. Browser smoke
  test confirmed rendering, drag rotation, visibility toggles and reset, with no
  browser error logs. Screenshot: `generated/scenes/phase2-demo/inspection.jpg`.
- Per-SWC 20 MB and aggregate-scene 100 MB limits. A missing v888 skeleton reports
  an error without publishing a partial scene. No new runtime dependencies.
- uv.lock/environment updated to version 0.3.0 using the existing offline cache.
- Final verification: 63 tests passed, Ruff check/format passed, and live
  `scene validate --scene generated/scenes/phase2-demo` succeeded offline.
- No commit/push performed.

Phase 3:

- Godot project with batched skeleton lines, orbit/pan/zoom/fit camera, line/list
  picking, selected-neuron metadata, incoming edge values, play/pause/reset/step.
- Offline bounded v1 loader verifies hashes, dataset/connectivity versions, exact
  string IDs, graph direction/costs, skeleton topology and coordinate bounds.
  Bad replacement scenes produce visible errors while retaining the current scene.
- Scientific caveats always visible. Playback highlights neurons without inventing
  inter-neuron cables, physiological timing or synapse positions.
- Windows export ACL issue found and fixed: private temporary-directory permissions
  survived publication, preventing the desktop Godot process from reading a sandbox
  export. New staging inherits normal destination permissions. Failure cleanup tested.
- Re-exported cached SWCs into `generated/scenes/phase3-demo/`: three real neurons,
  60,659 points / 60,656 branches, no simplification or new BANC download.
- Verified real OpenGL rendering on RTX 5070 Laptop GPU and inspected screenshots.
  Fixed a playback-label wrapping layout regression during the visual check.
  Screenshot: `generated/scenes/phase3-demo/godot-viewer.png`.
- Automated engine controls cover orbit, pan, zoom, line/list selection, stepping,
  timing/pause/reset/replay, invalid-load recovery and UI layout. OS input was not
  manually driven; the engine test invokes app input handlers and control signals.
- 78 Python/engine integration tests passed, including 14 optional Godot tests.
  Ruff checks and Python formatting passed. No new Python runtime dependency.
- Downloaded only the official Godot 4.7.2 Windows x64 portable ZIP (86,013,866
  bytes) into ignored `.tools/godot/`. No commit/push performed.

The file-based Phase 3 MVP is complete; Phase 4 below adds integrated queries.

Publication checkpoint (2026-10-02): user authorized commit/push after each phase.
Expanded ignore rules for raw SWCs/archives, tool binaries, environment variants,
credentials and Godot build state, preserving the tiny attributed test fixtures.
`scripts/check_repository.py --staged` audits exact index contents before publication
with a 2 MB per-file ceiling and high-confidence secret patterns. The completed
Phases 0–3 form one initial implementation checkpoint; subsequent phases receive
their own commits. No source datasets, generated scenes or tooling are published.

- Checkpoint `0f3a6df` pushed to `origin/main`; its GitHub Actions run completed
  successfully on the Windows/Linux Python matrix.

Phase 4:

- Optional FastAPI/Uvicorn service, fixed loopback binding, metadata facets and
  literal/paginated sensory/motor search. Source hashes/versions stay explicit.
- Single asynchronous path worker and one cached graph; threshold changes rebuild
  it. Concurrent submissions are rejected, not queued without bounds. Both modes
  export the existing validated scene contract and retain full provenance.
- Godot Explore tab: source/target search and explicit choices, body-part filters,
  proofread switch, threshold, mode comparison and optional selected-SWC fetching.
  Input changes clear stale selections/results; failures retain the displayed scene.
- Inspect tab and file-only viewing remain available. Comparison uses summaries
  and switching one viewport, with separate cost definitions and identical-route
  reporting. No physiological transmission/firing claims.
- Real offline UI/API run: SNta35 → IN03A009 → accessory_tibia_flexor_C, two hops
  in both modes, costs 2.0 (hops) / 11.0713 (normalized), 60,659 skeleton points.
  Current output examples are under `generated/api-phase4/`; screenshot is
  `docs/images/explorer-demo.png`. No BANC data was downloaded in this phase.
- Installed small optional API/test dependencies and updated the lock/environment
  to 0.4.0. Tests use HTTPX2, matching current Starlette's supported test client.
  Compressed dependency downloads were roughly 1.2 MB including the initial legacy
  HTTPX test-client attempt. API working set after the real two-mode run was about
  2.2 GB on this machine (one observation, not a peak-memory guarantee).
- 86 tests passed with Godot enabled, including synthetic real-HTTP Godot queries,
  both path objectives, offline guards, busy-job rejection, missing morphology,
  bad endpoints, no path, and recovery. Real GPU screenshot visually inspected.
- Python CI now installs the API extra. Godot's 15 optional integration tests are
  still local-only unless a CI runner supplies GODOT_BIN.

Phase 4 checkpoint `f05dd0f` pushed to `origin/main`; GitHub Actions passed.

Known limitations: no neuron meshes, synapse positions, raw EM, side-by-side
cameras or UI neuron removal. v2 is covered by synthetic tests but not live-validated.
The morphology provider has no automatic L2/legacy fallback. Equal-cost ties can
vary with igraph version. Server jobs finish even if the viewer closes; generated
output cleanup remains explicit. Restart the API after replacing source caches.

Phase 5 — selected scientific detail (neuropil spatial context):

- Verified official `region_outlines/` labels 3/4 (brain/VNC neuropil), legacy
  Neuroglancer binary layout and global-nm units. Parsed 6,722 vertices / 13,555
  triangles with no new dependency. These assets have independent unversioned
  provenance; they are not relabeled as v888 materialization data.
- Six bounded catalog/label/manifest/fragment files cached: 258,825 bytes excluding
  receipts. GCS stored fragment sizes total 148,323 bytes (gzip); returned fragment
  payloads were decompressed. Transfer/decompression capped at 5 MB/file. No neuron
  meshes, synapse table, EM, full atlas or bucket mirror downloaded.
- CLI `morphology context-fetch` and `scene export --include-context`; API/UI option
  for two context outlines, off by default. Offline runs only reuse verified caches.
- Scene schema 2 adds independently hashed context geometry with exact labels,
  counts, bounds and source receipts. Original schema 1 inputs are still accepted;
  exports without context retain the original shape for older Python readers.
- Godot batches two translucent surfaces and supports visibility toggle, Fit context
  and Fit path. Picking/playback still operates only on the selected neurons.
- Real three-neuron scene rendered on RTX 5070 Laptop GPU: 60,659 SWC points plus
  the two outlines. A real offline API job `5309260165d94ad88c308eee6cf803e1` computed
  and switched both modes with context; 22 automated UI/API checks passed. A separate
  GPU viewer check passed 43 checks. Screenshots were visually inspected; these are
  app-input automation checks, not manually driven OS mouse tests.
- Regression tests found and fixed Godot JSON float vs integer array-membership
  behavior in schema selection. Contracts still reject unsupported versions,
  unsafe paths, bad checksums, invalid triangles and false v888 context provenance.
- Current phase scope is complete with 109 Python/engine tests, Ruff and repository
  audit passing. The package version is 0.5.0. Documentation: `docs/context.md`;
  screenshot: `docs/images/context-demo.png`; generated files remain ignored.

Next milestone: investigate bounded, version-consistent selected-synapse evidence
and official EM ROI access before implementing Phase 6. Full synapse/EM downloads
remain prohibited without explicit approval; outlines do not provide synapse positions.
