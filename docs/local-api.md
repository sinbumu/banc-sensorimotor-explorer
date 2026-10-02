# Integrated local explorer (Phase 4)

Select sensory and motor neurons inside Godot, calculate one or both path modes,
then inspect the resulting real skeletons. Python still owns graph computation
and provenance. Godot consumes the validated v1/v2 scene bundles as the file MVP.

## Run

Complete the README's metadata/edge bootstrap first. No CAVE credentials are needed.
Install the optional API dependencies and start the service in one terminal:

```powershell
uv sync --locked --extra api
uv run --extra api banc-explorer serve
```

The CLI binds **127.0.0.1:8767** only. `--port` selects another local port;
`--config` selects a TOML config, including v2/v3 connectivity. Metadata is verified
at startup; connectivity is verified and loaded on the first query. Starting the
server never downloads core metadata or edges. A missing cache gives an actionable
`data prepare` error.

In a second terminal:

```powershell
.\scripts\run_viewer.ps1 -ApiUrl http://127.0.0.1:8767
```

An existing scene is optional. With the workspace demo present, its actual source
and target IDs seed the search boxes. Otherwise search by cell type, body part,
nerve, neuromere, side, functional annotation or decimal ID.

1. In **Explore**, search the sensory source and motor target. Body-part dropdowns
   apply exact category filters; text search is case-insensitive and literal.
2. Explicitly choose a result from each dropdown. It shows up to 50 matches;
   refine the query if the desired neuron is absent. IDs remain decimal strings.
3. Choose minimum hops or normalized strength, a minimum synapse count, and whether
   to calculate both modes. Proofread filtering applies to endpoints only.
4. Check **Fetch missing scene assets** to permit selected SWC downloads when needed.
   It is unchecked by default. Each SWC is bounded to 20 MB and each scene to
   100 MB total source SWCs. Optional **Include brain / VNC outlines** adds six
   bounded files (5 MB each maximum); see [context](context.md). No neuron mesh,
   synapse table or full archive is fetched.
5. Click **Find path**. Progress reports graph loading, calculation and skeleton
   preparation. The current scene stays visible until the new bundle validates.
6. Switch modes to view the corresponding reconstruction. Both summaries remain
   visible in Explore; their costs use different definitions and are not directly
   comparable numbers. Identical routes are explicitly reported as identical.
7. Click a skeleton to open **Inspect**, or use the tab to see annotations/edges.
   Existing camera and illustrative activation controls continue to work.

For the completely cached workspace demonstration, start the server with
`serve --offline`. The viewer then disables asset fetching. Known metadata IDs:
sensory `720575941350568496` (SNta35), motor `720575941463793552`
(accessory_tibia_flexor_C). These are a right middle-leg sensory annotation and
right hind-leg motor annotation; they are not asserted to form a behavioral route.
Both objectives currently select the same two-hop sequence through IN03A009.

The file-only CLI/viewer remains usable without installing the API extra. If a
plain `uv sync` removes optional packages, use `uv sync --extra api` again.
Stop the API before updating its environment on Windows, where a running
`banc-explorer.exe` launcher can lock the executable during dependency updates.

## API contract

| Route | Behavior |
|---|---|
| `GET /health` | Service/API version, BANC v888, connectivity version, offline flag, metadata hash, `em_available` |
| `GET /metadata/facets` | Sensory/effector body-part values from current cached metadata |
| `GET /neurons/search` | `kind`, `q`, `body_part`, `proofread_only`, `limit` (1–100), `offset` |
| `POST /paths` | Validate endpoint classes/options and start one bounded background job (202) |
| `GET /paths/{job_id}` | Queued/running/complete/error status and completed bundle locations |
| `POST /em` | Resolve a hash-verified cached SWC node and start a bounded EM job (202) |
| `GET /em/{job_id}` | Job status and completed `roi_directory`, transfer count and point IDs |
| `POST /interventions/path` | Compare filters against a completed baseline job, same mode/endpoints |
| `GET /interventions/{job_id}` | Reachability, before/after summary, report and optional scene locations |

Example request:

```json
{
  "source_id": "720575941350568496",
  "target_id": "720575941463793552",
  "modes": ["hops", "normalized"],
  "min_synapse_count": 5,
  "proofread_endpoints": true,
  "allow_downloads": false,
  "include_context": false
}
```

POST bodies require JSON and Content-Length and are capped at 4 KiB. Inputs cannot
specify output paths, remote data URLs, command strings or arbitrary versions.
Host checks restrict loopback names and cross-origin requests are rejected. This
is a desktop companion on a trusted local machine, not a hosted/multi-user service.
Do not expose it through a reverse proxy or LAN port forwarding.

Path, EM and intervention jobs share one worker. Only one job runs at a time; another submission receives 409 instead of queuing
unbounded work. One base graph is retained and reused for a compatible threshold;
intervention queries also build a temporary filtered graph. Each viewer route is
capped at 40 neurons. Larger intervention routes retain their graph report. The service
retains the last 32 job statuses in memory and keeps generated bundles on disk at
`generated/api/<job-id>/{hops,normalized}/` (or the explicit CLI `--output`).
Old files are not silently deleted. Stop the service before manually clearing
unneeded generated outputs. A restart clears job history and loaded graphs; saved
bundles still open through **Open scene…**. Restart after changing source caches.

Known no-path, missing-SWC and cache errors are returned as job errors, with the
existing viewer scene retained. Unexpected exceptions are logged on the server.
Closing the viewer does not cancel an already running server job. Progress is
polled, not a claimed percentage or latency estimate.

## Verification and limits

API tests use synthetic metadata, edges, SWCs and EM imagery. With `GODOT_BIN` set,
integration tests start a loopback HTTP server and drive actual Godot controls
through search, explicit selection, asynchronous computation, both mode loads and
stale-selection invalidation, exact SWC-point inspection and slice navigation.
No live BANC/network data is needed in CI.

```powershell
$env:GODOT_BIN = "$PWD/.tools/godot/Godot_v4.7.2-stable_win64_console.exe"
uv run --extra api pytest --basetemp .cache/pytest-api -o cache_dir=.cache/pytest-cache-api
```

The current verified real scene was regenerated through this UI/API route using
only cached v888 files; no manual path/export command was used for that run.
OpenGL rendering and screenshots were checked. These are automated app-input
checks plus visual inspection, not a manual OS-mouse test. The GitHub Python matrix
installs the API and EM extras; it does not currently install the optional Godot runtime.

Mode comparison uses summaries plus switching one 3D viewport. There are no two
simultaneous cameras or verified synapse positions. The [Intervene tab](interventions.md)
now supports neuron/type removal, threshold/side changes and before/after switching.

## Optional selected-point EM

Install and run with both extras: `uv sync --locked --extra api --extra em`, then
`uv run --extra api --extra em banc-explorer serve`. A plain `uv sync` can remove
optional packages. See [EM setup and provenance](em.md) for the full workflow.

`POST /em` accepts `neuron_id` (decimal string), `swc_node_id` (decimal string),
`swc_sha256` (from the displayed scene), `size_voxels` (default `[256,256,32]`),
`mip` (default 0), and `allow_downloads` (default false). It accepts no arbitrary
coordinates/URLs. The service verifies the cached source SWC and resolves the
actual node coordinates. Missing SWCs are errors, not automatic downloads.
EM fetching is separately controlled from scene-asset fetching and honors the
server offline flag. Files save in `generated/api/<job-id>/em/`; completed results
contain `roi_directory`, `downloaded_bytes`, `neuron_id` and `swc_node_id`.

References: [FastAPI lifespan](https://fastapi.tiangolo.com/advanced/events/),
[FastAPI testing](https://fastapi.tiangolo.com/tutorial/testing/),
[Godot HTTPRequest](https://docs.godotengine.org/en/stable/classes/class_httprequest.html).
