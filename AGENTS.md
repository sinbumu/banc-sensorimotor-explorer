# AGENTS.md — BANC Sensorimotor Explorer

> Main development instructions for coding agents working in this repository.
>
> Repository: `sinbumu/banc-sensorimotor-explorer`  
> Local workspace (primary developer machine): `C:\Users\user\Documents\GitHub\banc-sensorimotor-explorer`  
> Project type: personal RKS / research & self-study PoC  
> Primary platform: Windows 11  
> Initial document date: 2026-10-02

---

## 0. Read This First

This file is the authoritative development brief for this repository.

Before making non-trivial changes:

1. Read this file completely.
2. Inspect the current repository state (`git status`, tree, existing docs, tests).
3. Do not assume an API, dataset field, URL, or file format exists merely because it is mentioned in an old blog post or example.
4. Prefer the **public static BANC v888 release** for reproducible core analysis.
5. Keep the core application usable **without CAVE credentials**.
6. Do not silently download multi-GB datasets.
7. Do not commit raw BANC datasets, generated caches, credentials, or large binary exports.
8. Run relevant tests before declaring a phase complete.
9. Keep scientific claims conservative: this project visualizes graph-theoretic paths over a connectome; it does **not** claim to simulate biological neural dynamics.
10. The user explicitly authorized normal commits and pushes at each completed
    phase on 2026-10-02. Audit exclusions/secrets and run relevant checks first,
    then commit/push to the existing upstream and continue the next phase.
    Force-push, history rewriting, remote branch deletion and publishing releases
    still require separate explicit instructions.

If later instructions from the user conflict with this document, the user's latest explicit instruction wins. Update this document when a long-lived architectural decision changes.

---

# 1. Project Goal

Build an interactive local application that explores **sensory → motor pathways** in the adult female *Drosophila melanogaster* BANC (Brain And Nerve Cord) connectome and visualizes selected paths in a lightweight 3D environment.

The project should make a public connectome approachable as a visual, inspectable system:

```text
Sensory neuron
      │
      ▼
Interneuron(s)
      │
      ▼
Ascending / brain / descending circuit
      │
      ▼
VNC interneuron(s)
      │
      ▼
Motor neuron
```

The user should eventually be able to:

- choose or search a sensory neuron / sensory category;
- choose or search a motor neuron / effector body part;
- calculate a graph-theoretic pathway;
- compare a minimum-hop path with a connection-strength-aware path;
- inspect the neurons and edges in the chosen path;
- view their real reconstructed morphology as 3D skeletons;
- play an illustrative activation sequence through the path;
- optionally inspect synapse-level evidence and a small raw-EM region for selected connections;
- perform simple virtual interventions such as removing a neuron or increasing the connection threshold and recalculating the path.

The visual quality target is deliberately modest. A readable scientific/game-like 3D scene comparable to a simple Roblox/Minecraft-style prototype is enough. Correct data handling, clarity, and interactivity matter more than photorealism.

---

# 2. Non-Goals

Do **not** turn this project into any of the following unless the user explicitly expands scope:

- reconstructing the full BANC connectome from raw EM locally;
- training a whole-brain neuron segmentation model;
- downloading the entire raw EM volume;
- loading all individual synapses into RAM;
- rendering every neuron as a full-resolution mesh simultaneously;
- building a general-purpose neuroscience platform;
- reproducing every analysis from the BANC publication;
- implementing Hodgkin-Huxley or other biophysical whole-brain dynamics;
- claiming that shortest paths are actual information-flow routes;
- claiming that the signal animation is a physiological simulation;
- requiring cloud infrastructure or a hosted backend for the core demo;
- making CAVE authentication mandatory for the core pathfinding/3D demo.

Keep the project local-first and demonstrable.

---

# 3. Scientific/Data Baseline

## 3.1 Primary dataset

Use:

- **BANC — Brain And Nerve Cord**
- adult female *Drosophila melanogaster*
- baseline static snapshot: **CAVE materialization v888**
- publication snapshot: April 2026
- final Nature paper: Bates, Phelps, Kim, Yang et al. (2026), *Distributed control circuits across a brain-and-cord connectome*

BANC is especially appropriate because it spans both the brain and ventral nerve cord, enabling a single-connectome path from sensory input toward motor output.

The BANC dataset is a **living dataset**. Therefore distinguish:

- **reproducible baseline:** static v888 files used by this repository;
- **latest/live annotations:** Codex/CAVE, which may evolve.

Do not silently mix versions.

## 3.2 Core public files

Canonical public bucket prefix:

```text
gs://lee-lab_brain-and-nerve-cord-fly-connectome/
```

Core v888 files are under:

```text
compiled_data/banc_888/
```

Important files:

```text
banc_888_meta.feather
banc_888_metrics.feather
banc_888_edgelist_simple_v2.feather
banc_888_edgelist_simple_v3.feather
banc_888_edgelist_split_v2.feather
banc_888_synapses_v2_enriched.parquet
banc_888_synapses_v3_enriched.parquet
banc_888_neurotransmitter_prediction_v2.csv
```

Historical morphology assets live at the bucket root:

```text
neuron_skeletons/swcs-from-pcg-skel/
neuron_skeletons.zip
neuron_meshes/
region_outlines/
```

Verified during Phase 2 (2026-10-02): current v888 full skeletons are also available
at `compiled_data/banc_888/banc_banc_space_swc/<BANC_ID>_skeleton.swc` in nanometers.
Use this versioned source for scene exports. The legacy `swcs-from-pcg-skel`
sample used micrometers and did not contain the demo motor's v888 ID. Do not
silently fall back to legacy IDs/units; see `docs/morphology.md` for evidence.

Approximate sizes can change and must not be treated as schema invariants. At the time this document was prepared:

- metadata: ~49 MB;
- v3 neuron-neuron edge list: ~336 MB;
- zipped skeleton bundle: ~206 MB;
- per-synapse enriched tables: several GB each.

The core MVP should therefore operate on metadata + neuron-neuron edgelist + selected skeletons.

## 3.3 v2 versus v3 connectivity

The publication analyses primarily used the v2 synapse detector/table. New analyses may use v3.

Repository policy:

- default new exploratory graph: **v3 edgelist**;
- preserve support for **v2** as a reproducibility option;
- record the chosen connectivity version in every exported result;
- never compare v2 and v3 outputs without labeling which is which.

Do not hard-code conclusions from one version as if they are dataset-independent.

## 3.4 Important metadata fields

Verify the real schema at runtime before relying on it.

Expected useful fields include:

```text
banc_888_id
proofread
roughly_proofread
region
side
nerve
neuromere
flow
super_class
cell_class
cell_sub_class
cell_type
body_part_sensory
body_part_effector
peripheral_target_type
cell_function
cell_function_detailed
neurotransmitter_predicted
neurotransmitter_score
neurotransmitter_verified
status
```

Useful `super_class` values include categories such as:

```text
sensory
ascending
descending
intrinsic
motor
visceral_circulatory
ascending_visceral_circulatory
optic
```

For the initial project:

- sensory sources: start with `super_class == "sensory"`;
- motor targets: start with `super_class == "motor"`;
- broader effector support can be added later.

Never invent neuron IDs. Derive candidate IDs from the actual v888 metadata.

---

# 4. Source-of-Truth References

Use these references when an implementation detail needs verification.

Primary scientific/data references:

- Nature paper:  
  https://www.nature.com/articles/s41586-026-10735-w

- BANC project repository:  
  https://github.com/jasper-tms/the-BANC-fly-connectome

- BANC portal / project hub:  
  https://banc.community

- FlyWire Codex BANC explorer:  
  https://codex.flywire.ai/banc

- Static archive DOI / Harvard Dataverse:  
  https://doi.org/10.7910/DVN/7WTH1N

- Public data tutorial and BANC file documentation:  
  https://github.com/sjcabs/fly_connectome_data_tutorial

- Official/community Python package for BANC:  
  https://pypi.org/project/banc/

Data-access policy:

1. Prefer public static files for bulk/reproducible analysis.
2. Use Codex interactively for manual inspection and cross-checking, not as a bulk scraping target.
3. Use CAVE only for functionality that genuinely needs live/materialized queries, meshes, or raw-volume access.
4. Never require a private/authorized BANC credential for the core demo.
5. If CAVE or another external service changes, encapsulate it behind a provider interface rather than spreading API assumptions throughout the codebase.

---

# 5. Local Hardware Constraints

Design for the primary development laptop:

```text
CPU: Intel Core Ultra 9 275HX
RAM: 32 GB DDR5
GPU: NVIDIA GeForce RTX 5070 Laptop GPU
VRAM: ~8 GB
Storage: ~1 TB NVMe SSD
OS: Windows 11
```

Implications:

- metadata and the neuron-neuron edge list can be processed locally;
- full per-synapse tables must be filtered/lazily scanned rather than loaded wholesale;
- selected neuron skeletons are cheap;
- selected neuron meshes are reasonable;
- full-connectome high-detail mesh rendering is out of scope;
- GPU acceleration is not required for graph analysis;
- do not add CUDA/PyTorch merely because an NVIDIA GPU exists;
- leave headroom for Godot and the IDE while Python is running.

If an operation is expected to use multiple GB of disk/network or >10 GB RAM, report the estimate before starting it.

---

# 6. Architecture

Separate scientific/data computation from visualization.

Target architecture:

```text
                           BANC public data
                                  │
                     ┌────────────┴────────────┐
                     │                         │
              metadata / edges          skeletons / meshes
                     │                         │
                     ▼                         ▼
              Python data layer         morphology layer
                     │                         │
                     └────────────┬────────────┘
                                  ▼
                         graph/path engine
                                  │
                    ┌─────────────┴─────────────┐
                    │                           │
               CLI / tests               local API later
                    │                           │
                    └─────────────┬─────────────┘
                                  ▼
                         scene export contract
                                  │
                                  ▼
                              Godot 4
                                  │
                         interactive 3D viewer
```

Important principle:

> Godot is a viewer/controller, not the scientific-analysis engine.

Keep graph loading, filtering, pathfinding, provenance, and BANC-specific parsing in Python.

---

# 7. Preferred Technology Stack

## 7.1 Python

Target:

```text
Python 3.11 or 3.12
uv for environment/dependency management
```

Preferred libraries:

```text
polars              columnar metadata/edge processing
pyarrow             Feather/Parquet interoperability
fsspec + gcsfs      public GCS file access/caching
python-igraph       large directed graph/pathfinding
pydantic            typed interchange models
typer               CLI
rich                readable CLI output
trimesh             optional geometry/GLB generation
numpy               numeric operations
pytest              tests
```

Possible later additions:

```text
duckdb              selective local/remote Parquet exploration
fastapi + uvicorn   local viewer backend
cloud-volume        selected Neuroglancer-precomputed assets
caveclient          optional CAVE integration
banc                optional project-specific live tooling
```

Do not install every optional dependency at project bootstrap.

Keep heavyweight/live dependencies behind optional extras where practical, for example:

```toml
[project.optional-dependencies]
api = [...]
cave = [...]
dev = [...]
```

## 7.2 3D viewer

Use **Godot 4.x**.

Prefer:

```text
GDScript
MeshInstance3D / ArrayMesh / ImmediateMesh
Camera3D
Control-based UI
simple StandardMaterial3D / ShaderMaterial
```

Avoid premature custom rendering engines.

## 7.3 No hard requirement for ML frameworks

Do not add PyTorch, TensorFlow, CUDA kernels, or a GNN framework to the baseline project.

They are only justified if a later experiment explicitly needs them.

---

# 8. Proposed Repository Layout

Build toward this structure. Adapt only when there is a clear reason.

```text
banc-sensorimotor-explorer/
├── AGENTS.md
├── README.md
├── pyproject.toml
├── uv.lock
├── .python-version
├── .gitignore
├── configs/
│   └── default.toml
├── src/
│   └── banc_explorer/
│       ├── __init__.py
│       ├── config.py
│       ├── provenance.py
│       ├── models.py
│       ├── data/
│       │   ├── __init__.py
│       │   ├── catalog.py
│       │   ├── downloader.py
│       │   ├── metadata.py
│       │   ├── edges.py
│       │   └── cache.py
│       ├── graph/
│       │   ├── __init__.py
│       │   ├── build.py
│       │   ├── filters.py
│       │   ├── costs.py
│       │   ├── paths.py
│       │   └── interventions.py
│       ├── morphology/
│       │   ├── __init__.py
│       │   ├── swc.py
│       │   ├── transforms.py
│       │   ├── simplify.py
│       │   └── export.py
│       ├── synapses/
│       │   ├── __init__.py
│       │   └── evidence.py
│       ├── api/
│       │   ├── __init__.py
│       │   └── app.py
│       └── cli.py
├── scripts/
│   ├── bootstrap_data.py
│   └── build_demo.py
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
├── godot/
│   ├── project.godot
│   ├── scenes/
│   ├── scripts/
│   ├── materials/
│   └── assets/
├── generated/
│   └── .gitkeep
├── docs/
│   ├── architecture.md
│   ├── data.md
│   ├── scientific-notes.md
│   └── progress.md
└── .github/
    └── workflows/
        └── python-ci.yml
```

Do not create empty complexity merely to match this tree. Create modules as functionality appears.

---

# 9. Data and Cache Layout

Never put raw BANC data in tracked source directories.

Recommended local cache:

```text
.cache/
└── banc/
    └── v888/
        ├── metadata/
        ├── edges/
        ├── skeletons/
        ├── meshes/
        └── synapses/
```

Generated scene exports:

```text
generated/
└── scenes/
    └── <run-id>/
        ├── path.json
        ├── manifest.json
        ├── skeletons/
        └── geometry/
```

`.gitignore` must cover at least:

```gitignore
.cache/
.venv/
__pycache__/
.pytest_cache/
.ruff_cache/
generated/*
!generated/.gitkeep
*.feather
*.parquet
*.arrow
*.glb
*.gltf
*.bin
.env
*.token
cave-secret.json
```

Do not use a blanket rule that accidentally ignores intentional tiny test fixtures. Put fixtures under an explicitly allowed directory.

---

# 10. Reproducibility and Provenance

Every path calculation/export must record enough information to reproduce it.

A run manifest should include:

```json
{
  "dataset": "BANC",
  "materialization": 888,
  "connectivity_table": "v3",
  "metadata_source": "...",
  "edgelist_source": "...",
  "min_synapse_count": 5,
  "path_mode": "normalized_strength",
  "source_ids": [],
  "target_ids": [],
  "excluded_neurons": [],
  "filters": {},
  "created_at": "...",
  "software_version": "..."
}
```

If file hashes are cheap to compute, record them.

Never export a path without its dataset/materialization and path-cost definition.

---

# 11. Graph Semantics

The neuron-neuron graph is directed:

```text
pre  ──synapses──>  post
```

The graph edge should preserve at least:

```text
pre
post
count
norm
pre_count
post_count
```

Do not reverse direction accidentally.

## 11.1 Default filtering

Initial sane defaults:

- exclude edges below a configurable minimum `count`;
- start with `min_synapse_count = 5` for a Codex-like noise guard;
- optionally restrict sources/targets to proofread neurons for curated demos;
- retain the ability to disable proofread filtering for exploration;
- log all filters.

Do not permanently drop weak edges from the cached source dataset. Apply filters during graph construction/query.

---

# 12. Path Modes

The app must distinguish graph objectives instead of calling everything "shortest path".

## 12.1 Mode A — minimum hop count

Purpose:

> Find a path using the fewest neuron-to-neuron transitions.

Edge cost:

```text
1
```

Use BFS/unweighted shortest-path logic.

Display:

```text
Minimum-hop path
5 hops
```

Do not describe this as the "most likely biological route".

## 12.2 Mode B — connection-strength-aware path

A raw synapse count can be misleading because large target neurons naturally have many inputs.

Preferred initial normalized edge quantity:

```text
norm = count / post_count
```

A useful path cost is:

```text
cost = -log(max(norm, epsilon))
```

Then minimizing total cost is equivalent to maximizing the product of normalized edge contributions.

Important:

- call this a **normalized-strength path** or similar;
- do **not** call `norm` a transmission probability;
- do **not** claim the resulting product is a physiological probability;
- document epsilon and numerical handling.

Keep raw-count alternatives available for experimentation, e.g.:

```text
raw_count_cost = 1 / log1p(count)
```

but do not make arbitrary metrics scientifically authoritative.

## 12.3 Later — alternative paths

After the first two modes work:

- k-shortest alternatives;
- avoid-one-neuron path;
- side-constrained paths;
- body-part-constrained paths;
- paths constrained by cell/super classes.

Do not implement all variants before the basic end-to-end demo exists.

---

# 13. Source and Target Selection

## 13.1 Initial demo

Do not hard-code guessed biological IDs from memory or documentation.

Instead:

1. load actual v888 metadata;
2. inspect source candidates with:
   - `super_class == "sensory"`;
   - preferably `proofread == true`;
   - a clear `body_part_sensory`, nerve, cell type, or functional annotation;
3. inspect target candidates with:
   - `super_class == "motor"`;
   - preferably `proofread == true`;
   - a clear `body_part_effector`, neuromere, nerve, or muscle-related annotation;
4. choose a pair/group that actually has a path under a reasonable threshold;
5. record the IDs and selection rationale in a generated demo config, not in core code.

A leg-related sensory→motor example is a good candidate if the real data supports it, but do not force this narrative if the metadata/path is poor.

## 13.2 Category-level selection

After explicit-ID pathfinding works, add user-facing selection by:

```text
body_part_sensory
body_part_effector
nerve
neuromere
cell_type
cell_function
side
```

For many-source/many-target queries, use an efficient multi-source/multi-target strategy rather than running an O(N×M) loop.

---

# 14. Morphology / Skeleton Handling

## 14.1 MVP uses SWC skeletons

Default morphology source:

```text
compiled_data/banc_888/banc_banc_space_swc/<BANC_ID>_skeleton.swc
```

This source uses nm; SWC is not universally nm. The parser must require explicit
source units and normalize them to nm internally. Missing v888 morphology must
produce an actionable error, not an automatic older-materialization substitution.

Fetch only selected path neurons unless the user explicitly requests the full skeleton archive.

Implement an internal skeleton model such as:

```python
class SkeletonNode:
    id: int
    label: int
    xyz_nm: tuple[float, float, float]
    radius_nm: float
    parent_id: int | None
```

Validate:

- parent references;
- finite coordinates;
- one or more roots;
- no accidental unit conversion;
- no impossible index assumptions.

## 14.2 Coordinate transform

BANC coordinates can be numerically large and are not directly convenient as Godot world units.

Centralize the transform in one module.

Suggested principle:

```text
1 Godot unit = 10 µm = 10,000 nm
```

but determine the final scale after inspecting an actual skeleton/outline.

Transform pipeline:

```text
BANC nm coordinates
      │
subtract common origin / scene center
      │
axis mapping into Godot coordinates
      │
uniform scale into Godot units
      ▼
Godot world coordinates
```

Godot is Y-up. Do not scatter ad-hoc axis swaps throughout code.

Store transform metadata with every exported scene:

```json
{
  "source_units": "nm",
  "world_units": "godot_unit",
  "nm_per_world_unit": 10000,
  "origin_nm": [0, 0, 0],
  "axis_map": "..."
}
```

Provide a tested forward transform. Add an inverse transform if later EM/synapse picking needs it.

## 14.3 Simplification

For interactive display:

- preserve gross morphology;
- simplify dense skeleton samples if needed;
- do not change neuron topology accidentally;
- keep raw cached SWC separate from simplified/generated geometry.

---

# 15. 3D Rendering Strategy

## 15.1 First visual milestone

Render selected pathway neurons as colored skeleton line/tube structures in a free-camera Godot scene.

Required:

- orbit/fly camera;
- transparent or dark neutral background;
- each neuron distinguishable;
- selected neuron highlighting;
- basic brain/VNC spatial orientation if possible;
- labels/panel showing neuron ID and metadata.

Do not wait for full meshes.

## 15.2 Geometry

Start with efficient line geometry:

- one `ArrayMesh` or similar per neuron;
- batch segments where practical;
- avoid one Node3D per SWC point.

If thin lines are unreadable, generate low-poly tubes offline in Python or use a lightweight shader-based approach.

Full-resolution neuron meshes are an optional detail mode, not the baseline.

## 15.3 CNS context

Use `region_outlines/` if practical.

Desired scene:

- transparent/simplified CNS outline;
- path neurons overlaid inside;
- brain / cervical connective / VNC spatial relationship readable.

If the official outline format takes too long to integrate, use a temporary simple context representation and track the real outline import as a separate milestone.

---

# 16. Signal / Activation Visualization

The animation is illustrative.

Do **not** pretend a graph edge is a literal straight cable from one soma to another.

Initial animation:

1. highlight neuron 1;
2. fade/highlight neuron 2;
3. proceed through the path;
4. show the edge synapse count and normalized contribution in the UI;
5. optionally place a connection marker if a real synapse coordinate is available.

UI wording should say things such as:

```text
Illustrative path activation
Graph step 3 / 6
Connection: 47 synapses
Normalized input contribution: 0.083
```

Avoid:

```text
Real neural firing
Exact biological signal
83% probability
```

Later, if per-synapse coordinates are loaded, show true spatial synapse markers and animate the transition around those markers.

---

# 17. Synapse-Level Evidence

Synapse-level data is a later phase because the enriched tables are several GB.

Rules:

- never load the whole enriched synapse table into RAM;
- do not automatically download the entire table;
- use predicate pushdown / selective queries when possible;
- query only selected `pre`/`post` path pairs or spatial regions;
- cache tiny extracted subsets.

A selected-edge evidence model should contain:

```text
pre_root_id
post_root_id
synapse_id
x/y/z
region / neuropil
side
optional neurotransmitter fields
```

If using v3 path edges with v2 synapse evidence, label the mismatch and do not silently treat them as the same detector/version.

Prefer version-consistent evidence where feasible.

---

# 18. Raw EM Mode

Raw EM is optional and must not block the main demo.

Goal:

> For a selected synapse/point, show a small original-EM ROI to demonstrate the anatomical source behind the reconstruction.

Do not download the full EM volume.

Implement as a provider abstraction:

```python
class EmProvider(Protocol):
    def fetch_roi(self, center_nm, size_voxels, mip=...) -> EmVolume:
        ...
```

Potential official routes include BANC Neuroglancer/CAVE and archived public imagery. Verify current access at implementation time.

Default ROI should be small, for example on the order of:

```text
256 × 256 × 32 or 64 voxels
```

Choose dimensions based on actual voxel spacing, latency, and visual clarity.

Raw EM mode is considered successful if the user can click/select a known location and inspect a small slice/stack. It does not need real-time volumetric raymarching.

---

# 19. Virtual Intervention Mode

After base paths work, add simple graph interventions.

Examples:

```text
disable neuron
exclude cell type
increase minimum synapse count
restrict to left/right side
exclude one super_class
```

Then recalculate and compare:

```text
Before:
Sensory → A → B → Motor
4 hops

After removing B:
Sensory → C → D → E → Motor
5 hops
```

Always label this as a **graph intervention**, not a predicted experimental phenotype.

Useful outputs:

- old vs new hop count;
- old vs new path cost;
- nodes removed/added;
- whether no path remains.

---

# 20. Python CLI

Before building a complex UI/backend, provide a reliable CLI.

Target commands may evolve, but aim for functionality similar to:

```powershell
uv run banc-explorer data prepare
uv run banc-explorer data validate
uv run banc-explorer candidates sensory --body-part "..."
uv run banc-explorer candidates motor --body-part "..."
uv run banc-explorer path find --source-id <id> --target-id <id> --mode hops
uv run banc-explorer path find --source-id <id> --target-id <id> --mode normalized
uv run banc-explorer morphology fetch --id <id>
uv run banc-explorer scene export --path <path-result>
uv run banc-explorer demo build
```

Every command should:

- provide actionable errors;
- avoid giant stack traces for expected user errors;
- show when a download is happening;
- show destination paths;
- reuse cache;
- report dataset/materialization/version.

---

# 21. Python ↔ Godot Contract

Do not tightly couple Godot to Python internals.

Start with a file-based scene contract.

Suggested `path.json`:

```json
{
  "schema_version": 1,
  "run": {
    "dataset": "BANC",
    "materialization": 888,
    "connectivity_version": "v3",
    "path_mode": "normalized_strength",
    "min_synapse_count": 5
  },
  "source": {
    "id": 123,
    "label": "..."
  },
  "target": {
    "id": 456,
    "label": "..."
  },
  "neurons": [
    {
      "id": 123,
      "order": 0,
      "cell_type": "...",
      "super_class": "sensory",
      "region": "...",
      "skeleton": "skeletons/123.json"
    }
  ],
  "edges": [
    {
      "pre": 123,
      "post": 234,
      "count": 47,
      "norm": 0.083,
      "cost": 2.48
    }
  ],
  "coordinate_transform": {
    "source_units": "nm",
    "nm_per_world_unit": 10000,
    "origin_nm": [0, 0, 0],
    "axis_map": "..."
  }
}
```

Validate this contract with Pydantic before writing.

Implementation decision (2026-10-02): serialize neuron IDs as decimal strings in
JSON, including edge endpoints and manifest ID lists. Keep exact integer IDs in
Python. The numeric IDs in the illustrative example above must not be parsed
through floating-point JSON values: real BANC IDs exceed JavaScript's exact integer
range. Phase 1 exports `artifact_type: "graph_path"` with `schema_version: 1`;
this graph-only result is not yet a morphology-bearing Godot scene contract.

Normalized-strength costs use recomputed `count / post_count` with unfiltered
source totals. Retain the public table's rounded value as `norm` and export the
recomputed value as `normalized_input`, with epsilon and cost definition recorded.

The Godot parser must reject unsupported schema versions with a clear message.

---

# 22. Local API — Only After File-Based MVP

Once the static export workflow is reliable, add a local API if dynamic selection inside Godot is needed.

Possible endpoints:

```text
GET  /health
GET  /metadata/facets
GET  /neurons/search
GET  /neurons/{id}
POST /paths
GET  /paths/{run_id}
GET  /neurons/{id}/skeleton
POST /interventions/path
```

The API should bind to localhost by default.

Do not build user accounts, authentication, cloud hosting, or a database server for this PoC.

---

# 23. User Interface Target

A practical layout:

```text
┌─────────────────────────────────────────────────────────────┐
│ BANC Sensorimotor Explorer                                  │
├───────────────────────────────┬─────────────────────────────┤
│                               │ Source                      │
│                               │ [sensory selector]          │
│                               │                             │
│          3D VIEW              │ Target                      │
│                               │ [motor selector]            │
│                               │                             │
│                               │ Path Mode                   │
│                               │ ( ) Min hops                │
│                               │ ( ) Normalized strength     │
│                               │                             │
│                               │ Min synapses [ 5 ]          │
│                               │                             │
│                               │ [Find Path]                 │
├───────────────────────────────┼─────────────────────────────┤
│ [Play] [Pause] [Reset]        │ Path: 6 neurons / 5 hops    │
│                               │ Selected neuron metadata    │
└───────────────────────────────┴─────────────────────────────┘
```

Later add:

```text
Compare modes
Intervention
Synapse evidence
EM view
```

Do not clutter the first demo.

---

# 24. Scientific Integrity Rules

These are mandatory.

## 24.1 Wording

Use:

- "graph-theoretic path";
- "minimum-hop path";
- "normalized-strength path";
- "illustrative activation";
- "connectome-derived";
- "reconstructed morphology";
- "predicted neurotransmitter" where appropriate.

Avoid unsupported language such as:

- "the signal actually travels through this route";
- "this is the fly's decision pathway";
- "this neuron causes this motor behavior";
- "the shortest path is the biological pathway";
- "this animation simulates real neural firing".

## 24.2 Neurotransmitters

Do not create a simplistic global rule such as:

```text
acetylcholine = always excitatory
GABA = always inhibitory
glutamate = always inhibitory
```

and present it as biological truth.

If a later toy activity model uses signs, explicitly call it a simplification and document the assumptions.

## 24.3 Path strength

`norm = count / post_count` is a normalized structural contribution, not a synaptic transmission probability.

The `-log(norm)` path metric is an analysis choice, not an experimentally validated neural likelihood model.

---

# 25. Data Safety / Download Guardrails

The agent must not surprise the user with large downloads.

Before any single download expected to exceed ~1 GB:

1. print/report the expected file and approximate size;
2. explain why it is required;
3. prefer streaming/filtering/on-demand alternatives;
4. get explicit approval if a full download is still necessary.

Core bootstrap should remain well below this threshold.

Do not recursively mirror the BANC public bucket.

Do not bulk-fetch full meshes for all neurons.

Do not bulk-fetch raw EM.

---

# 26. Credential Handling

Core MVP must require no secrets.

If optional CAVE functionality is added:

- never commit tokens;
- never paste a token into source code;
- use the standard CAVE credential mechanism or environment/config outside Git;
- document setup separately;
- keep credentialed code behind an optional provider;
- degrade gracefully if credentials are absent.

`.gitignore` must cover common secret files.

---

# 27. Testing Strategy

## 27.1 Unit tests

At minimum test:

- metadata schema normalization;
- edge filtering;
- graph direction;
- cost formulas;
- shortest-path correctness on a hand-built toy graph;
- normalized-strength path correctness on a hand-built toy graph;
- intervention exclusion;
- SWC parsing;
- coordinate transforms;
- path manifest serialization/deserialization.

## 27.2 Integration tests

Use small cached/fixture subsets, not the full dataset in CI.

Test:

```text
fixture metadata
+ fixture edges
→ candidate lookup
→ path
→ selected skeleton
→ scene export
```

If live public-data tests are added, mark them separately so standard CI is deterministic.

## 27.3 Visual smoke test

Maintain one known small generated scene that can be regenerated from fixtures.

Godot should be able to open/load the path contract without parser errors.

Do not store a huge generated demo in Git merely for tests.

---

# 28. Logging and Error Handling

Use normal Python logging rather than scattered prints in library code.

CLI may use Rich for presentation.

Useful messages:

```text
Using BANC materialization 888
Connectivity: v3
Loaded metadata: ...
Loaded edges: ...
Applied min_synapse_count >= 5
Graph: ... vertices / ... edges
Path found: 5 hops
Fetching 6 skeletons (4 cached, 2 remote)
Scene exported to ...
```

Expected failures should be understandable:

```text
No directed path exists under the current threshold.
Try lowering min_synapse_count or changing the target.
```

Avoid hiding exceptions during development. Wrap only expected user-facing failure modes.

---

# 29. Performance Rules

The 32 GB laptop is capable but not unlimited.

Do:

- use columnar data;
- select only needed columns;
- use categorical/integer IDs efficiently;
- use `python-igraph` rather than Python-object-heavy graph structures for the full graph;
- cache processed graph artifacts if benchmark evidence shows useful startup savings;
- lazy/filter per-synapse Parquet;
- load path skeletons on demand;
- unload/reuse Godot geometry when paths change.

Avoid:

- building millions of Python dictionaries for edges;
- full per-synapse Pandas DataFrames;
- one Godot scene node per skeleton point;
- one draw call per tiny segment if batching is easy;
- GPU-compute complexity without a measured need.

Profile before optimizing further.

---

# 30. Windows Development Rules

The primary workspace is Windows-native.

Prefer commands that work in PowerShell.

Examples:

```powershell
uv sync
uv run pytest
uv run banc-explorer --help
```

Do not assume:

```text
bash-only scripts
/usr/bin paths
brew
apt
Linux-only symlinks
```

Cross-platform Python is preferred.

WSL may be documented as an optional path for a dependency that is materially easier on Linux, but the baseline demo should not require switching environments.

---

# 31. Git / Repository Rules

The repository is currently a personal public GitHub project.

Before edits:

```powershell
git status
git branch --show-current
```

Do not:

- force-push;
- reset/delete user work;
- amend unrelated commits;
- commit datasets;
- commit secrets;
- push outside the phase-completion workflow authorized below.

Standing user instruction (2026-10-02): after each phase, verify `.gitignore`,
audit the exact staged files for data/caches/secrets, run relevant checks, then
make a focused commit and normal push to the existing upstream. Continue the
next phase after that checkpoint. Do not request the same authorization again.
The first checkpoint captures the already completed Phases 0–3 together; do not
invent a retroactive development history. A failed/non-fast-forward push must
be diagnosed without force-pushing or discarding work.

Keep commits focused if the user asks the agent to commit.

Good commit boundaries:

```text
chore: bootstrap Python project and data catalog
feat: add BANC metadata and connectivity loader
feat: implement sensory-to-motor pathfinding
feat: add SWC morphology export
feat: add Godot path viewer
feat: add illustrative path playback
```

---

# 32. Documentation Rules

Keep README useful to an outside GitHub visitor.

README should eventually answer:

1. What is this?
2. What is BANC?
3. What does the demo actually do?
4. What does it *not* claim?
5. How do I install/run it?
6. What data does it download?
7. How do I reproduce the example?
8. What are the data/paper citations?
9. What screenshots/GIF show the result?

Track deeper details in:

```text
docs/data.md
docs/architecture.md
docs/scientific-notes.md
```

Maintain `docs/progress.md` as a lightweight phase/status record if development spans multiple sessions.

---

# 33. Development Phases

Do not attempt all features at once.

## Phase 0 — Bootstrap and Data Validation

Goal:

> Prove that v888 public data can be fetched, cached, opened, and understood on the target Windows machine.

Tasks:

- initialize Python project with `uv`;
- create `.gitignore`;
- add config/data catalog;
- download/cache metadata;
- download/cache one edgelist version (default v3);
- inspect and validate schemas;
- produce CLI data summary;
- write first tests;
- document exact public sources.

Definition of done:

```text
uv run banc-explorer data validate
```

succeeds and reports dataset version, rows/columns, key fields, and cache paths.

No Godot work is required yet.

---

## Phase 1 — Graph and Pathfinding

Goal:

> Reliably compute sensory→motor paths.

Tasks:

- normalize BANC IDs to an integer type safely;
- build directed igraph;
- implement configurable edge threshold;
- implement minimum-hop path;
- implement normalized-strength path;
- expose candidate sensory/motor metadata search;
- select a real demonstration pair from the dataset;
- export a path result JSON;
- add tests using a toy graph and a small real-data sample.

Definition of done:

The CLI can calculate two path modes between the same real source/target and display:

```text
node sequence
cell labels/classes
edge synapse counts
norm
hop count
total selected cost
```

---

## Phase 2 — Skeleton Pipeline

Goal:

> Turn a computed path into real BANC 3D morphology.

Tasks:

- fetch selected SWCs;
- parse/validate SWC;
- centralize BANC→Godot coordinate transform;
- optionally simplify morphology;
- export Godot-friendly geometry/JSON;
- create reproducible scene manifest.

Definition of done:

A path of several neurons can be exported with valid spatial morphology and opened by a simple local inspection script or viewer.

---

## Phase 3 — Godot 3D MVP

Goal:

> Interactive 3D path viewer.

Tasks:

- create Godot project;
- load exported path manifest;
- render each neuron;
- implement orbit/fly camera;
- highlight selected neuron;
- basic metadata panel;
- play/pause/reset illustrative activation sequence;
- show edge count/norm while stepping through path.

Definition of done:

A user can launch Godot, view the real reconstructed morphology for a computed sensory→motor path, rotate the camera, click/step through neurons, and play the path sequence.

This is the first major public demo milestone.

---

## Phase 4 — Integrated Local Explorer

Goal:

> Choose source/target from the UI instead of regenerating scene files manually.

Possible tasks:

- add local FastAPI service;
- expose metadata facets/search;
- call path engine dynamically;
- fetch/cache skeletons dynamically;
- reload viewer scene on query;
- compare hop vs strength-aware path side by side.

Definition of done:

A user can select a source/target in the application and generate a new path without manually running a build script.

---

## Phase 5 — Scientific Detail

Add selectively:

- CNS region outlines;
- actual synapse coordinates for selected path edges;
- selected neuron full mesh mode;
- v2/v3 comparison;
- neurotransmitter metadata display;
- k-shortest alternatives.

Do not make these prerequisites for earlier phases.

---

## Phase 6 — EM Evidence

Goal:

> Trace selected reconstructed connections back to a small raw-EM context.

Tasks:

- verify current official raw-EM access;
- add provider abstraction;
- fetch a tiny ROI around a selected synapse;
- display orthogonal/slice view;
- record coordinate/version provenance.

No whole-volume download.

---

## Phase 7 — Intervention Playground

Goal:

> Make graph structure explorable.

Add:

- remove neuron;
- remove cell type;
- change minimum synapse threshold;
- side restriction;
- recalculate path;
- visualize before/after.

Keep claims graph-theoretic.

---

# 34. Recommended First Demo Story

The first public demo should tell one clear story, not expose every feature.

Suggested flow:

```text
1. Select one well-annotated sensory neuron.
2. Select one well-annotated motor neuron.
3. Show minimum-hop path.
4. Switch to normalized-strength path.
5. Explain why the paths may differ.
6. Open 3D view using real BANC skeletons.
7. Play illustrative activation sequence.
8. Click one neuron to show metadata.
9. Change synapse threshold or disable one path neuron.
10. Recalculate and show the alternate structural route.
```

If later synapse/EM evidence is ready:

```text
11. Select a connection.
12. Show actual synapse coordinate(s).
13. Open a small raw-EM ROI.
```

This is enough for a strong RKS demonstration.

---

# 35. Definition of "MVP Complete"

Do not call the project MVP complete until all of these are true:

- [x] BANC v888 source/version is explicit.
- [x] Core data bootstrap is reproducible.
- [x] No private credential is needed for core use.
- [x] Real sensory and motor neurons are selected from metadata.
- [x] Directed pathfinding works.
- [x] Minimum-hop and normalized-strength modes are distinct.
- [x] Every displayed edge has real BANC connectivity values.
- [x] Selected neurons use real BANC skeleton morphology.
- [x] Coordinate conversion is documented/tested.
- [x] Godot loads and renders a path.
- [x] Camera interaction works.
- [x] Illustrative path playback works.
- [x] Scientific caveats are visible in docs/UI.
- [x] Data/cache files are not tracked by Git.
- [x] Core Python tests pass.
- [x] README explains setup and demo.

Verified 2026-10-02: file-based Phase 3 MVP, 78 Python/engine tests, real GPU
rendering and automated camera/control smoke checks. See `docs/progress.md` and
`docs/godot.md` for evidence and limitations. Phase 4 now adds integrated static-v888
metadata selection and local path queries; 86 tests including HTTP/Godot integration
passed. See `docs/local-api.md`. This remains a static snapshot, not live CAVE data.

Raw EM is **not** required for MVP completion.

---

# 36. Initial Implementation Order for the Main Agent

When starting from the currently empty repository, proceed in this order unless a blocker requires a small detour:

1. Inspect Git/repository.
2. Create minimal Python project scaffolding.
3. Create `.gitignore`.
4. Add `configs/default.toml`.
5. Implement BANC v888 data catalog.
6. Implement small public download/cache utility.
7. Download metadata only.
8. Inspect/validate metadata schema.
9. Add sensory/motor candidate CLI.
10. Download v3 edgelist.
11. Inspect/validate edge schema.
12. Build directed igraph.
13. Add toy-graph path tests.
14. Implement minimum-hop path.
15. Implement normalized-strength path.
16. Find one real source/target demo pair.
17. Export path JSON + provenance.
18. Fetch SWCs for the path only.
19. Parse and convert skeleton coordinates.
20. Export viewer contract.
21. Bootstrap Godot project.
22. Render path morphology.
23. Add path playback.
24. Add README screenshots/demo instructions.
25. Only then consider API integration, meshes, synapse evidence, and raw EM.

At every major boundary, leave the repository runnable.

---

# 37. Decision Log: Defaults Already Chosen

Unless the user changes them, treat these as project decisions:

| Topic | Decision |
|---|---|
| Connectome | BANC |
| Reproducible baseline | materialization v888 |
| Default new graph | v3 neuron-neuron edgelist |
| Publication comparison | v2 supported |
| Core data access | public static files |
| Live CAVE | optional |
| Core source class | sensory |
| Core target class | motor |
| Graph library | python-igraph |
| Dataframes | Polars / PyArrow |
| Python env | uv |
| Viewer | Godot 4 |
| Viewer language | GDScript |
| Viewer integration first | file-based manifest |
| Local API | later, FastAPI if needed |
| Morphology first | SWC skeleton |
| Full mesh | optional detail mode |
| Raw EM | optional later phase |
| Whole-EM reconstruction | out of scope |
| Signal visualization | illustrative only |

If changing one of these decisions, document the reason in `docs/architecture.md` or a small ADR-style note.

---

# 38. Quality Bar

This is a toy/research project, but do not treat "toy" as permission for fragile code.

Prioritize:

1. reproducibility;
2. scientific clarity;
3. an end-to-end working demo;
4. understandable code;
5. visible results;
6. reasonable performance.

Avoid premature enterprise architecture.

A simple correct pipeline is better than an elaborate unfinished one.

---

# 39. Agent Completion Reports

At the end of each substantial work session, report:

```text
What changed
- ...

What was verified
- tests:
- commands:
- visual/manual checks:

Data/network actions
- files downloaded:
- approximate size:
- cache path:

Known limitations
- ...

Next recommended step
- ...
```

If blocked by external data/API behavior, provide:

- exact attempted source;
- exact error;
- whether it is auth, network, schema, or code;
- a fallback path.

Do not conceal incomplete work behind vague statements such as "mostly done".

---

# 40. Final Reminder

The strongest version of this project is not "a fake fly brain simulator."

It is:

> **An interactive 3D explorer that computes and visualizes graph-theoretic sensory-to-motor routes over a real, synapse-resolution Drosophila brain-and-nerve-cord connectome, with progressively deeper access to reconstructed morphology, synapse evidence, and raw EM context.**

Build that first.

Everything else is optional expansion.
