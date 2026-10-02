# Godot 3D viewer

The Phase 3 viewer consumes a validated Python `skeleton_scene` v1 bundle. It is
offline and has no Python process, CAVE credentials, API server or network dependency
at runtime. Graph computation remains in Python. Phase 4 adds an optional
[localhost explorer](local-api.md) in the Explore tab; the file mode described here
continues to work independently.

## Launch on Windows

Use the standard GDScript build of [Godot 4 for Windows](https://godotengine.org/download/windows/).
The verified workspace runtime is **4.7.2.stable.official.ed1daf0bf**, downloaded
from the official link into ignored `.tools/godot/` (86,013,866 compressed bytes).
No system installation, .NET build or export templates are needed.

From the repository root:

```powershell
# Existing verified workspace bundle and local portable Godot:
.\scripts\run_viewer.ps1

# Any other Python-exported bundle and Godot installation:
.\scripts\run_viewer.ps1 -Scene generated/scenes/my-demo -Godot C:\Tools\Godot\Godot.exe
```

The script defaults to `generated/scenes/phase3-demo`. It searches `GODOT_BIN`,
the workspace portable executable, then `godot` on PATH. The direct equivalent is:

```powershell
& $env:GODOT_BIN --path godot -- --scene-dir "$PWD/generated/scenes/phase3-demo"
```

Alternatively import `godot/project.godot` into the Godot editor and press F6/F5
with the main scene. If the workspace demo is absent, the empty viewer explains
how to build a bundle; **Open scene…** accepts a bundle's `manifest.json` or
`path.json`. The entire bundle must remain together.

For a fresh checkout, run the README data setup, then:

```powershell
uv run banc-explorer demo build --body-part leg --output generated/phase1-demo
uv run banc-explorer scene export --path generated/phase1-demo/normalized.json --output generated/scenes/phase3-demo
uv run banc-explorer scene validate --scene generated/scenes/phase3-demo
.\scripts\run_viewer.ps1
```

Existing output destinations are protected; choose new names for subsequent runs.
Scene export fetches only path SWCs; add `--offline` when they are already cached.
To view the minimum-hop result, export `hops.json` into another bundle and open
its manifest. Threshold/exclusion changes also require a new Python path/export.

## Controls

| Action | Control |
|---|---|
| Orbit | Left drag in the 3D viewport |
| Pan | Right or middle drag |
| Zoom | Mouse wheel |
| Fit all geometry | Fit camera / F |
| Select neuron | Click near its skeleton, or its list row |
| Illustrative playback | Play / Pause; Space when viewport has focus |
| Inspect adjacent graph step | Previous / Next; left/right arrows |
| Reset activation | Reset / Home |
| Show all colors equally | Equal brightness checkbox |

The active neuron is bright; other neurons are dimmed. Selection displays exact
root ID, annotations, point/root counts and the incoming directed edge. For the
source there is no incoming path edge. Displayed normalized input is the exact
`count/post_count` ratio; the rounded source-table norm is labeled separately.
The mode, threshold, connectivity version and total cost remain visible.

Playback highlights whole neurons in path order at a configurable **illustrative**
interval. It stops at the target; Play from the target starts again at the source.
Changing selection pauses playback. There are no invented soma-to-soma cables,
transmission probabilities or claims of physiological timing.

## Rendering and validation

- One MeshInstance3D / ArrayMesh per neuron, batched parent-child line segments;
  isolated SWC roots use a point surface. No node per SWC point.
- Unshaded materials, OpenGL Compatibility renderer, 4× MSAA. Fixed line width
  and isolated point size are display choices, not measured neurite thickness.
- Orthographic orbit camera fits projected bounds. Geometry is already in the
  common Python coordinate frame; Godot never recenters individual neurons or
  applies the transform a second time. Y-up is a display convention.
- SHA-256 verification of scene, original graph result and every geometry file;
  schema/version, string ID, directed edge/cost, bounds and iterative forest checks.
  Unsupported schemas produce clear errors; an invalid replacement leaves the
  currently displayed scene intact.
- Viewer budgets: 128 MiB per JSON file, 256 MiB total JSON, one million points.
  Loading is synchronous; the selected three-neuron scene is small enough for
  this prototype. Larger scenes may pause the UI and may need simplification.
- Screen-space selection chooses the nearest projected branch within 9 pixels.
  Overlapping neurons can be selected unambiguously through the list.

Optional [brain/VNC neuropil outlines](context.md) now provide spatial context.
Anatomical dorsal/ventral axes are not asserted. The viewer has no
synapse locations, raw EM, meshes or neuron removal control. A localhost selection
and query service is now available through the optional API extra. The file workflow supports results
of Python threshold/exclusion queries.

## Verification

Standard Python tests require no engine or downloads. To also run the deterministic
Godot integration suite (14 tests), set the executable path:

```powershell
$env:GODOT_BIN = "$PWD/.tools/godot/Godot_v4.7.2-stable_win64_console.exe"
uv run pytest --basetemp .cache/pytest-godot -o cache_dir=.cache/pytest-cache-godot
```

Without `GODOT_BIN`, those 20 tests are explicitly skipped (plus one HTTP/Godot
integration test when the API extra is installed). The current Python CI does not
install Godot. Engine tests use tiny synthetic scenes and no public data.
They exercise Python → Godot loading, IDs above 2^53, both cost modes, directed
edges, checksum/schema/topology rejection, zero-hop/isolated-root scenes, camera
input handlers, list/click selection, pause/reset/replay and failed-load recovery.
The wrapper fails on engine error logs as well as nonzero exit codes.

To run the same control smoke test with the real cached scene:

```powershell
& $env:GODOT_BIN --headless --path godot --script res://tests/smoke.gd -- --scene-dir "$PWD/generated/scenes/phase3-demo"
```

For a real GPU screenshot, omit `--headless` and add
`--screenshot "$PWD/generated/scenes/phase3-demo/godot-viewer.png"` after `--`.
The script drives app signals/input handlers, checks behavior, captures the viewport
and exits. It is an automated functional/visual smoke test, not a manual OS-input
test. The verified renderer is OpenGL 3.3 on the RTX 5070 Laptop GPU; other platforms
have not been visually checked. The current local screenshot is
`generated/scenes/phase3-demo/godot-viewer.png` (untracked).

The earlier Python TemporaryDirectory-based staging inherited an owner-only ACL
on Windows when exported by a sandbox account. New exports use a unique sibling
directory with normal inherited destination permissions, validate it, then rename
it atomically. If an old bundle is unreadable from the desktop, re-export into a
fresh directory; changing global filesystem permissions is unnecessary.

Implementation references: [ArrayMesh](https://docs.godotengine.org/en/stable/classes/class_arraymesh.html),
[point rendering](https://docs.godotengine.org/en/stable/classes/class_basematerial3d.html#class-basematerial3d-property-use-point-size),
[command-line usage](https://docs.godotengine.org/en/stable/tutorials/editor/command_line_tutorial.html).
