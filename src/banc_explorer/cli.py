"""The data validate command is offline and never implicitly downloads."""

import json
import logging
from datetime import UTC, datetime
from functools import wraps
from pathlib import Path
from typing import Annotated
from urllib.error import URLError

import polars as pl
import pyarrow as pa
import typer
from rich.console import Console

from banc_explorer.config import load_settings
from banc_explorer.data.catalog import METADATA, edgelist
from banc_explorer.data.downloader import download, verify_cache
from banc_explorer.data.metadata import candidates as select_candidates
from banc_explorer.data.metadata import load_metadata
from banc_explorer.graph.costs import PathMode
from banc_explorer.models import PathResult
from banc_explorer.provenance import write_result
from banc_explorer.workflow import export_demo, open_session

app = typer.Typer(no_args_is_help=True)
data = typer.Typer(no_args_is_help=True)
app.add_typer(data, name="data")
path_app = typer.Typer(no_args_is_help=True)
demo_app = typer.Typer(no_args_is_help=True)
app.add_typer(path_app, name="path")
app.add_typer(demo_app, name="demo")
morphology_app = typer.Typer(no_args_is_help=True)
app.add_typer(morphology_app, name="morphology")
scene_app = typer.Typer(no_args_is_help=True)
app.add_typer(scene_app, name="scene")
console = Console()
Config = Annotated[Path | None, typer.Option(help="TOML configuration file.")]


def friendly(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except (ValueError, OSError, URLError, pl.exceptions.PolarsError, pa.ArrowException) as exc:
            console.print(f"Error: {exc}", style="red", markup=False)
            raise typer.Exit(1) from None

    return wrapped


@app.command("serve")
@friendly
def serve(
    config: Config = None,
    port: Annotated[int, typer.Option(min=1024, max=65535)] = 8767,
    output: Path = Path("generated/api"),
    offline: bool = False,
):
    """Run the optional local explorer API on 127.0.0.1 only."""
    try:
        import uvicorn

        from banc_explorer.api.app import create_app
    except ImportError:
        raise ValueError("Install the local API extra: uv sync --extra api") from None
    settings = load_settings(config)
    # Surface missing metadata as a normal CLI error before starting the server.
    verify_cache(METADATA, settings.cache_dir)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    console.print(f"BANC v888 / {settings.connectivity_version}; local API http://127.0.0.1:{port}")
    console.print(f"Scene outputs: {output.resolve()}", markup=False)
    uvicorn.run(create_app(settings, output, offline=offline), host="127.0.0.1", port=port)


@morphology_app.command("fetch")
@friendly
def morphology_fetch(
    neuron_id: Annotated[int, typer.Option("--id", min=1)],
    config: Config = None,
    offline: bool = False,
    refresh: bool = False,
):
    """Fetch/validate one v888 SWC; never substitute older root IDs."""
    from banc_explorer.data.catalog import skeleton
    from banc_explorer.morphology.provider import fetch_skeleton

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    settings = load_settings(config)
    parsed, _ = fetch_skeleton(neuron_id, settings.cache_dir, offline=offline, refresh=refresh)
    console.print(f"BANC v888 morphology: {len(parsed.nodes)} nodes, {len(parsed.roots)} roots; nm")
    console.print(str(skeleton(neuron_id).local_path(settings.cache_dir).resolve()), markup=False)


@morphology_app.command("context-fetch")
@friendly
def context_fetch(config: Config = None, offline: bool = False, refresh: bool = False):
    """Cache two public neuropil outlines, independent of v888 materialization."""
    from banc_explorer.morphology.context import fetch_context

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    cache = load_settings(config).cache_dir
    for item in fetch_context(cache, offline=offline, refresh=refresh):
        console.print(
            f"{item['label']}: {len(item['points_nm'])} vertices / {len(item['triangles'])} triangles; source nm; unversioned context"
        )
    console.print(str((cache / "context").resolve()), markup=False)


@scene_app.command("export")
@friendly
def scene_export(
    path: Annotated[Path, typer.Option()],
    output: Path | None = None,
    config: Config = None,
    offline: bool = False,
    nm_per_world_unit: float = 10000,
    include_context: bool = False,
):
    """Export selected v888 skeletons with one common coordinate transform."""
    from banc_explorer.morphology.export import export_scene

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    destination = output if output is not None else Path("generated/scenes") / run_directory().name
    result = export_scene(
        path,
        destination,
        load_settings(config).cache_dir,
        offline=offline,
        nm_per_world_unit=nm_per_world_unit,
        include_context=include_context,
    )
    console.print(
        f"BANC v888 scene: {len(result.neurons)} neurons; "
        f"{sum(n.node_count for n in result.neurons)} nodes; no simplification"
    )
    console.print(f"Saved: {destination.resolve()}", markup=False)


@scene_app.command("validate")
@friendly
def scene_validate(scene: Annotated[Path, typer.Option()]):
    """Validate an exported bundle offline, including topology and file hashes."""
    from banc_explorer.morphology.export import load_scene

    result, _ = load_scene(scene)
    console.print(
        f"Valid BANC v888 skeleton scene: {len(result.neurons)} neurons / "
        f"{sum(n.node_count for n in result.neurons)} nodes; "
        f"{result.coordinate_transform.nm_per_world_unit:g} nm per world unit"
    )


@scene_app.command("inspect")
@friendly
def scene_inspect(scene: Annotated[Path, typer.Option()], output: Path | None = None):
    """Create a self-contained HTML inspection aid from a validated scene."""
    from banc_explorer.morphology.preview import write_preview

    destination = output if output is not None else scene / "inspection.html"
    write_preview(scene, destination)
    console.print(f"Open in a browser: {destination.resolve()}", markup=False)


@data.command()
@friendly
def prepare(config: Config = None, metadata_only: bool = False, refresh: bool = False):
    """Fetch metadata and the selected v2/v3 edgelist into the verified cache."""
    settings = load_settings(config)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    console.print(f"BANC v888 / connectivity {settings.connectivity_version}")
    assets = [METADATA] if metadata_only else [METADATA, edgelist(settings.connectivity_version)]
    for asset in assets:
        download(asset, settings.cache_dir, max_bytes=settings.max_download_bytes, refresh=refresh)


@data.command()
@friendly
def validate(config: Config = None, metadata_only: bool = False, output: Path | None = None):
    """Verify cache hashes, schema and values; optionally save a JSON report."""
    from banc_explorer.data.edges import filter_edges, load_edges

    settings = load_settings(config)
    report = {
        "dataset": "BANC",
        "materialization": 888,
        "connectivity_version": settings.connectivity_version,
        "files": [],
    }
    assets = [METADATA] if metadata_only else [METADATA, edgelist(settings.connectivity_version)]
    for asset in assets:
        receipt = verify_cache(asset, settings.cache_dir)
        path = asset.local_path(settings.cache_dir)
        frame = load_metadata(path) if asset == METADATA else load_edges(path)
        entry = {
            "path": str(path.resolve()),
            "rows": frame.height,
            "columns": {k: str(v) for k, v in frame.schema.items()},
            "receipt": receipt,
        }
        if asset == METADATA:
            entry["classes"] = frame.group_by("super_class").len().sort("super_class").to_dicts()
            entry["proofread_sensory"] = select_candidates(frame, "sensory").height
            entry["proofread_motor"] = select_candidates(frame, "motor").height
        else:
            entry["min_synapse_count"] = settings.min_synapse_count
            entry["edges_at_threshold"] = filter_edges(frame, settings.min_synapse_count).height
        report["files"].append(entry)
        del frame
    rendered = json.dumps(report, indent=2)
    console.print(rendered, markup=False, highlight=False)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")


@app.command()
@friendly
def candidates(
    kind: str,
    config: Config = None,
    body_part: str | None = None,
    all_quality: bool = False,
    limit: Annotated[int, typer.Option(min=1)] = 20,
):
    """List real sensory/motor IDs; proofread-only unless --all-quality is set."""
    settings = load_settings(config)
    verify_cache(METADATA, settings.cache_dir)
    frame = load_metadata(METADATA.local_path(settings.cache_dir))
    result = select_candidates(frame, kind, body_part=body_part, proofread_only=not all_quality)
    fields = [
        x
        for x in [
            "banc_888_id",
            "proofread",
            "super_class",
            "cell_type",
            "side",
            "nerve",
            "body_part_sensory",
            "body_part_effector",
        ]
        if x in frame.columns
    ]
    console.print(f"BANC v888 | {result.height} matches; showing up to {limit}")
    console.print(
        json.dumps(result.select(fields).head(limit).to_dicts(), indent=2),
        markup=False,
        highlight=False,
    )


def show_path(result: PathResult) -> None:
    title = (
        "Minimum-hop path"
        if result.manifest.path_mode == PathMode.hops
        else "Normalized-strength path"
    )
    console.print(f"{title}: {result.hop_count} hops; total cost {result.total_cost:.9g}")
    for i, neuron in enumerate(result.neurons):
        console.print(
            f"{i}: {neuron.id} | {neuron.cell_type or 'unlabeled'} | "
            f"{neuron.super_class or 'unknown class'}",
            markup=False,
        )
        if i < len(result.edges):
            edge = result.edges[i]
            console.print(
                f"  -> count={edge.count}; norm(source)={edge.norm:.9g}; "
                f"count/post_count={edge.normalized_input:.9g}; cost={edge.cost:.9g}"
            )
    console.print(result.interpretation)


def run_directory() -> Path:
    return Path("generated/paths") / datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")


@path_app.command("find")
@friendly
def find(
    source_id: Annotated[int, typer.Option(min=1)],
    target_id: Annotated[int, typer.Option(min=1)],
    mode: PathMode = PathMode.hops,
    config: Config = None,
    min_synapse_count: Annotated[int | None, typer.Option(min=1)] = None,
    exclude_id: Annotated[
        list[int] | None, typer.Option(help="Repeat to exclude multiple neurons.")
    ] = None,
    proofread_endpoints: bool = False,
    output: Path | None = None,
):
    """Find a directed graph-theoretic path and export its validated provenance."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    destination = output if output is not None else run_directory() / "path.json"
    if destination.exists():
        raise ValueError(f"Output already exists: {destination}. Choose a new path.")
    settings = load_settings(config)
    if min_synapse_count is not None:
        settings.min_synapse_count = min_synapse_count
    session = open_session(settings, excluded_neurons=tuple(exclude_id or []))
    result = session.calculate(source_id, target_id, mode, proofread_endpoints)
    write_result(result, destination)
    show_path(result)
    console.print(f"Saved: {destination.resolve()}", markup=False)


@demo_app.command("build")
@friendly
def demo_build(
    config: Config = None,
    body_part: str = "leg",
    max_sources: Annotated[int, typer.Option(min=1)] = 25,
    output: Path | None = None,
):
    """Select real proofread candidates and export both modes using one loaded graph."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    destination = output if output is not None else run_directory()
    if destination.exists():
        raise ValueError(f"Output already exists: {destination}. Choose a new directory.")
    results = export_demo(
        open_session(load_settings(config)),
        destination,
        body_part=body_part or None,
        max_sources=max_sources,
    )
    for result in results:
        show_path(result)
    console.print(f"Demo and selection rationale: {destination.resolve()}", markup=False)
