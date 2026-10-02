# Progress — 2026-10-02

Phases 0–3 implemented and verified on Windows Python 3.12 and Godot 4.7.2.

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

The file-based Phase 3 MVP is complete. Limitations: live source/target queries
remain a CLI/export workflow; no CNS outline, meshes, synapse positions or EM view.
v2 is covered by synthetic integration tests but not live-validated. The morphology
provider has no automatic L2/legacy fallback. GitHub CI has not run and does not
currently install Godot. Equal-cost ties can vary with igraph version.

Next milestone: Phase 4 local source/target selection and path recalculation from
the viewer, retaining the validated file contract and public static v888 baseline.

Publication checkpoint (2026-10-02): user authorized commit/push after each phase.
Expanded ignore rules for raw SWCs/archives, tool binaries, environment variants,
credentials and Godot build state, preserving the tiny attributed test fixtures.
`scripts/check_repository.py --staged` audits exact index contents before publication
with a 2 MB per-file ceiling and high-confidence secret patterns. The completed
Phases 0–3 form one initial implementation checkpoint; subsequent phases receive
their own commits. No source datasets, generated scenes or tooling are published.
