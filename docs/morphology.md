# Morphology sources and scene contract

## Source verification (2026-10-02)

The original tutorial/brief's root-level `neuron_skeletons/swcs-from-pcg-skel/`
path cannot be assumed to be a v888 nm source. We fetched a 1,348-byte diagnostic
SWC for sensory ID 720575941350568496. Its root `(433.984, 820.464, 108.720)`
matches metadata `root_position_nm = (433984, 820464, 108720)` only after multiplying
by 1,000. The demo motor ID 720575941463793552 returns HTTP 404 at that source;
metadata lists a different `root_626`. That diagnostic remains an ignored cache
file and is not used by the scene provider.

Bounded listings of the official public bucket confirmed this versioned directory:

```text
https://storage.googleapis.com/lee-lab_brain-and-nerve-cord-fly-connectome/compiled_data/banc_888/banc_banc_space_swc/
```

The selected neurons all have `<v888_id>_skeleton.swc` files. `<id>_l2.swc` and
`<id>.swc` probes returned 404 for these three IDs; other IDs can have L2 files.
Only the verified full-SWC provider is implemented. Missing full files fail clearly;
no root-626 crosswalk or legacy morphology fallback occurs.

| v888 neuron ID | SWC bytes | Points | Roots | Generation |
|---|---:|---:|---:|---|
| 720575941350568496 | 107,204 | 1,646 | 1 | 1777944219079965 |
| 720575941557376164 | 1,216,460 | 18,223 | 1 | 1777944998319924 |
| 720575941463793552 | 2,760,853 | 40,790 | 1 | 1777944447341441 |

Their coordinates are in BANC nm space. As a scale/alignment sanity check, the
nearest SWC points to each neuron's metadata `root_position_nm` were approximately
177, 239 and 377 nm away, respectively. This supports the nm interpretation; it
does not establish biological accuracy or synapse localization. The generated
`coordinate-check.json` records this one-time diagnostic and transform bounds.

Full source URLs and SHA-256 hashes are embedded per neuron in exported scenes.
Object generations and hashes matter even inside a versioned directory, since
upstream compiled objects may be replaced. Receipts capture materialization 888.
No CAVE credentials are used.

## Parsing and coordinates

The SWC reader requires explicit `source_units="nm"` or `"um"`. Coordinates and
radii normalize to nm internally. It supports comments, zero-based/non-contiguous
IDs, unordered rows and forests. It rejects duplicate IDs, missing parents, cycles,
empty skeletons, negative radii and non-finite coordinates/radii. A root has parent
`-1`; every other parent is resolved by ID, never by row arithmetic. Zero radius
is preserved. The parser checks forests iteratively to support long chains.

All skeletons in a scene share one origin: the center of their combined bounding
box. Do not center each neuron separately. Given `q = xyz_nm - origin_nm`, the
default transform is:

```text
world = (q.x, -q.z, q.y) / 10000
nm    = origin_nm + (world.x, world.z, -world.y) * 10000
```

This is a right-handed axis rotation into a Y-up display frame, followed by uniform
scaling. Display Y corresponds to negative BANC Z; no anatomical dorsal/anterior
claim is implied. `1 Godot unit = 10 µm`. `--nm-per-world-unit` can override the
scale and must be positive/finite. The forward/inverse transform is tested.
Radii are uniformly scaled without applying the origin or axis mapping.

No simplification is performed: all 60,659 points and 60,656 parent branches in
the selected real scene survive export. The full path's spatial extent is roughly
173 × 154 × 416 µm in display X/Y/Z. Synthetic integration tests verify that
relative offsets between neurons and their forest topology survive conversion.

## Bundle layout

```text
<scene>/
  path.json                  skeleton_scene v1 descriptor
  graph-path.json            byte-for-byte original graph_path v1 input
  manifest.json              timestamp, exporter version, hashes of both files
  skeletons/<neuron_id>.json  geometry and original SWC node identity
  inspection.html            optional, self-contained offline inspection aid
```

`path.json` contains the validated `path_result`, ordered `neurons` references,
`coordinate_transform`, `bounds_min`, `bounds_max` and `simplification: "none"`.
Each neuron reference includes ID/order, relative skeleton path, geometry hash,
node/root counts and original SWC source URL/hash/bytes/generation/units/version.

Each geometry file has `schema_version: 1`, exact string `neuron_id`, string
`node_ids`, `labels`, world-unit `points`, world-unit `radii`, and dense-index
`parents`. Parent `null` means root; a branch connects point i to point parents[i].
Original SWC IDs can be unordered or zero-based; only dense parent indices refer
to arrays. Godot should batch these branches per neuron rather than create a
Node3D for every point. Both artifact types must reject unsupported schema versions.

Every bundle is validated before publication into a fresh output directory.
Offline loading checks file hashes, reference paths, IDs/counts, topology, bounds
and consistency with the embedded/original graph result. Paths that escape the
bundle are rejected. Hashes provide integrity detection, not signed authenticity.
Incomplete fetch/export attempts do not leave a successful scene directory.

## Inspection and current limits

`scene inspect` validates the bundle, then creates an offline HTML canvas preview
with orthographic rotation, zoom, per-neuron visibility and reset. It embeds only
the selected morphology and needs no third-party scripts/network. Metadata is
escaped into JSON and rendered as text. Line widths are for visibility; SWC radii
remain in the geometry. Root markers identify SWC roots, not asserted somata.

The inspection aid is not the Godot MVP and has no neural activation simulation.
No CNS outline, mesh surface or true synapse marker is shown. Graph connections
are not rendered as straight inter-neuron cables. Godot loading and illustrative
path playback belong to Phase 3.

Tests include an eight-node real v888 SWC excerpt with source attribution in its
header; it is intentionally truncated and must not be presented as a whole neuron.
