"""Graph result contract. JSON neuron IDs are strings to avoid float precision loss."""

import math
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, PlainSerializer, model_validator

from banc_explorer.graph.costs import PathMode, cost_definition, normalized_cost


def parse_id(value):
    if isinstance(value, str) and value.isascii() and value.isdecimal():
        value = int(value)
    if type(value) is not int or not 0 < value < 2**64:
        raise ValueError("Neuron ID must be a positive UInt64 integer or decimal string.")
    return value


NeuronId = Annotated[int, BeforeValidator(parse_id), PlainSerializer(str, when_used="json")]
PositiveCount = Annotated[int, Field(strict=True, gt=0)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class SourceFile(Contract):
    url: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    bytes: int = Field(gt=0)
    generation: str | None = None


class Manifest(Contract):
    dataset: Literal["BANC"] = "BANC"
    materialization: Literal[888] = 888
    connectivity_version: Literal["v2", "v3"]
    metadata_source: SourceFile
    edgelist_source: SourceFile
    min_synapse_count: PositiveCount
    path_mode: PathMode
    cost_definition: str
    norm_definition: Literal["count/post_count using unfiltered source totals"] = (
        "count/post_count using unfiltered source totals"
    )
    epsilon: float = Field(gt=0, le=1)
    source_ids: list[NeuronId] = Field(min_length=1, max_length=1)
    target_ids: list[NeuronId] = Field(min_length=1, max_length=1)
    excluded_neurons: list[NeuronId]
    filters: dict
    graph_vertices: int = Field(ge=0)
    graph_edges: int = Field(ge=0)
    coverage: dict
    created_at: datetime
    software_version: str
    igraph_version: str

    @model_validator(mode="after")
    def check_definition(self):
        if self.cost_definition != cost_definition(self.path_mode):
            raise ValueError("Cost definition disagrees with path mode.")
        return self


class PathNeuron(Contract):
    id: NeuronId
    metadata_available: bool
    cell_type: str | None = None
    super_class: str | None = None
    region: str | None = None
    side: str | None = None
    nerve: str | None = None
    body_part_sensory: str | None = None
    body_part_effector: str | None = None
    proofread: bool | None = None


class PathEdge(Contract):
    pre: NeuronId
    post: NeuronId
    count: PositiveCount
    pre_count: PositiveCount
    post_count: PositiveCount
    norm: float = Field(gt=0, le=1, description="Original rounded public-table value")
    normalized_input: float = Field(gt=0, le=1, description="Recomputed count/post_count")
    cost: float = Field(ge=0)

    @model_validator(mode="after")
    def check_ratio(self):
        if self.count > min(self.pre_count, self.post_count):
            raise ValueError("Edge count exceeds source/target total.")
        if not math.isclose(self.normalized_input, self.count / self.post_count, rel_tol=1e-12):
            raise ValueError("Normalized input disagrees with count/post_count.")
        if abs(self.norm - self.normalized_input) > 5.1e-5:
            raise ValueError("Source norm disagrees with count/post_count beyond rounding.")
        return self


class PathResult(Contract):
    schema_version: Literal[1] = 1
    artifact_type: Literal["graph_path"] = "graph_path"
    manifest: Manifest
    neurons: list[PathNeuron] = Field(min_length=1)
    edges: list[PathEdge]
    hop_count: int = Field(ge=0)
    total_cost: float = Field(ge=0)
    interpretation: Literal["Structural graph-theoretic path; not a physiological probability."] = (
        "Structural graph-theoretic path; not a physiological probability."
    )

    @model_validator(mode="after")
    def check_path(self):
        ids = [n.id for n in self.neurons]
        if (
            len(self.edges) != self.hop_count
            or len(ids) != self.hop_count + 1
            or len(set(ids)) != len(ids)
        ):
            raise ValueError("Path length or repeated-neuron inconsistency.")
        if ids[0] != self.manifest.source_ids[0] or ids[-1] != self.manifest.target_ids[0]:
            raise ValueError("Path endpoints disagree with manifest.")
        if set(ids) & set(self.manifest.excluded_neurons):
            raise ValueError("Path contains an excluded neuron.")
        for i, edge in enumerate(self.edges):
            if (edge.pre, edge.post) != (ids[i], ids[i + 1]):
                raise ValueError("Path edges must follow directed neuron order.")
            if edge.count < self.manifest.min_synapse_count:
                raise ValueError("Path edge violates threshold.")
            expected = (
                1
                if self.manifest.path_mode == PathMode.hops
                else normalized_cost(edge.normalized_input, self.manifest.epsilon)
            )
            if not math.isclose(edge.cost, expected, abs_tol=1e-12):
                raise ValueError("Path edge cost disagrees with cost definition.")
        if not math.isclose(self.total_cost, math.fsum(e.cost for e in self.edges), abs_tol=1e-12):
            raise ValueError("Total path cost disagrees with edge costs.")
        return self
