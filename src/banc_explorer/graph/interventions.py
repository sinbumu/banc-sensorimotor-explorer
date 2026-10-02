"""Reproducible structural graph interventions; no phenotype prediction."""

from typing import Literal

import polars as pl
from pydantic import Field, model_validator

from banc_explorer.graph.build import filtered_graph
from banc_explorer.graph.costs import PathMode
from banc_explorer.graph.paths import NoPathError
from banc_explorer.models import Contract, Manifest, NeuronId, PathResult
from banc_explorer.provenance import make_manifest
from banc_explorer.workflow import Session


class InterventionRules(Contract):
    min_synapse_count: int = Field(default=5, ge=1, le=100000, strict=True)
    excluded_neurons: list[NeuronId] = Field(default_factory=list, max_length=40)
    excluded_cell_types: list[str] = Field(default_factory=list, max_length=10)
    side: Literal["left", "right"] | None = None

    @model_validator(mode="after")
    def validate_rules(self):
        if any(not value.strip() or len(value) > 120 for value in self.excluded_cell_types):
            raise ValueError(
                "Excluded cell types require exact nonempty labels (max 120 characters)."
            )
        self.excluded_neurons = sorted(set(self.excluded_neurons))
        self.excluded_cell_types = sorted(set(self.excluded_cell_types))
        return self


class InterventionRequest(InterventionRules):
    baseline_job_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    mode: PathMode
    allow_downloads: bool = False


class InterventionReport(Contract):
    schema_version: Literal[1] = 1
    artifact_type: Literal["graph_intervention"] = "graph_intervention"
    interpretation: Literal[
        "Structural graph intervention; not a predicted experimental phenotype."
    ] = "Structural graph intervention; not a predicted experimental phenotype."
    rules: InterventionRules
    before: PathResult
    after: PathResult | None
    after_manifest: Manifest
    no_path_reason: Literal["endpoint_filtered", "no_directed_path"] | None = None

    @model_validator(mode="after")
    def validate_comparison(self):
        a, b = self.before.manifest, self.after_manifest
        for name in [
            "metadata_source",
            "edgelist_source",
            "connectivity_version",
            "path_mode",
            "epsilon",
            "source_ids",
            "target_ids",
            "cost_definition",
            "norm_definition",
        ]:
            if getattr(a, name) != getattr(b, name):
                raise ValueError(f"Intervention comparison changed {name}.")
        if b.min_synapse_count != self.rules.min_synapse_count:
            raise ValueError("Intervention threshold disagrees with query provenance.")
        if b.filters.get("intervention") != self.rules.model_dump(mode="json"):
            raise ValueError("Intervention rules disagree with query provenance.")
        if (self.after is None) != (self.no_path_reason is not None):
            raise ValueError("Intervention reachability/reason mismatch.")
        if self.after is not None and self.after.manifest != b:
            raise ValueError("Intervention path/query provenance mismatch.")
        endpoint_filtered = bool(set(b.source_ids + b.target_ids) & set(b.excluded_neurons))
        if self.no_path_reason == "endpoint_filtered" and not endpoint_filtered:
            raise ValueError("Filtered-endpoint reason requires an excluded endpoint.")
        if self.no_path_reason == "no_directed_path" and endpoint_filtered:
            raise ValueError("An excluded endpoint must be labeled endpoint_filtered.")
        return self

    def summary(self):
        before_ids = [str(n.id) for n in self.before.neurons]
        after_ids = [str(n.id) for n in self.after.neurons] if self.after else []
        return dict(
            reachable=self.after is not None,
            no_path_reason=self.no_path_reason,
            mode=self.before.manifest.path_mode.value,
            before_hops=self.before.hop_count,
            before_cost=self.before.total_cost,
            after_hops=self.after.hop_count if self.after else None,
            after_cost=self.after.total_cost if self.after else None,
            before_ids=before_ids,
            after_ids=after_ids,
            removed_ids=[n for n in before_ids if n not in after_ids] if self.after else [],
            added_ids=[n for n in after_ids if n not in before_ids],
            filtered_neuron_count=len(self.after_manifest.excluded_neurons),
        )


def resolve_exclusions(session: Session, rules: InterventionRules) -> list[int]:
    graph = session.graph
    excluded = set(rules.excluded_neurons)
    if excluded - set(graph.ids):
        raise ValueError("Excluded neuron ID is absent from this dataset.")
    metadata = graph.metadata
    if rules.excluded_cell_types:
        if "cell_type" not in metadata.columns or set(rules.excluded_cell_types) - set(
            metadata["cell_type"].drop_nulls()
        ):
            raise ValueError(
                "Excluded cell type is absent from the cached metadata; use its exact label."
            )
        excluded.update(
            metadata.filter(pl.col("cell_type").is_in(rules.excluded_cell_types))["banc_888_id"]
        )
    if rules.side:
        if "side" not in metadata.columns:
            raise ValueError("Side annotations are unavailable in this metadata.")
        allowed = set(metadata.filter(pl.col("side") == rules.side)["banc_888_id"])
        # Restriction applies to every vertex, including endpoints. Unknown side is excluded.
        excluded.update(set(graph.ids) - allowed)
    return sorted(excluded)


def compare_intervention(
    session: Session, before: PathResult, rules: InterventionRules
) -> InterventionReport:
    baseline = before.manifest
    if (
        session.settings.connectivity_version != baseline.connectivity_version
        or session.metadata_receipt["sha256"] != baseline.metadata_source.sha256
        or session.edges_receipt["sha256"] != baseline.edgelist_source.sha256
    ):
        raise ValueError("Baseline source changed; calculate a fresh baseline before comparing.")
    if session.graph.min_synapse_count > rules.min_synapse_count or session.graph.excluded_neurons:
        raise ValueError("Intervention requires an unmodified graph at or below the new threshold.")
    excluded = resolve_exclusions(session, rules)
    graph = filtered_graph(
        session.graph, min_synapse_count=rules.min_synapse_count, excluded_neurons=excluded
    )
    source, target = baseline.source_ids[0], baseline.target_ids[0]
    curated = baseline.filters.get("proofread_endpoints", False)
    manifest = make_manifest(
        graph,
        source,
        target,
        baseline.path_mode,
        version=baseline.connectivity_version,
        metadata_receipt=session.metadata_receipt,
        edges_receipt=session.edges_receipt,
        epsilon=baseline.epsilon,
        proofread_endpoints=curated,
    )
    manifest.filters.update(
        intervention=rules.model_dump(mode="json"),
        intermediate_neuron_filter="recorded graph intervention",
        metadata_missing_policy="exclude unknown side" if rules.side else "retain",
        side_scope="all vertices including endpoints" if rules.side else None,
    )
    modified = Session(
        graph,
        session.settings.model_copy(
            update={"min_synapse_count": rules.min_synapse_count, "epsilon": baseline.epsilon}
        ),
        session.metadata_receipt,
        session.edges_receipt,
    )
    after, reason = None, None
    if source in excluded or target in excluded:
        reason = "endpoint_filtered"
    else:
        try:
            result = modified.calculate(source, target, baseline.path_mode, curated)
            after = PathResult.model_validate(result.model_dump() | {"manifest": manifest})
        except NoPathError:
            reason = "no_directed_path"
    return InterventionReport(
        rules=rules, before=before, after=after, after_manifest=manifest, no_path_reason=reason
    )
