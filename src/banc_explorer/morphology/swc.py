"""SWC parser supporting forests, zero-based and unordered node IDs."""

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class SkeletonNode:
    id: int
    label: int
    xyz_nm: tuple[float, float, float]
    radius_nm: float
    parent_id: int | None


@dataclass(frozen=True)
class Skeleton:
    nodes: tuple[SkeletonNode, ...]
    source_units: Literal["nm", "um"]

    @property
    def roots(self) -> tuple[int, ...]:
        return tuple(n.id for n in self.nodes if n.parent_id is None)


def validate_parents(ids: list[int], parents: list[int | None]) -> None:
    if not ids or len(ids) != len(parents):
        raise ValueError("Skeleton must contain nodes and one parent entry per node.")
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate SWC node ID.")
    links = dict(zip(ids, parents, strict=True))
    if not any(parent is None for parent in parents):
        raise ValueError("Skeleton must have at least one root (parent -1).")
    for node, parent in links.items():
        if parent is not None and parent not in links:
            raise ValueError(f"Node {node} references missing parent {parent}.")
    # Iterative O(N) forest check; no recursion depth limit for long branches.
    done = set()
    for node in ids:
        chain = set()
        while node is not None and node not in done:
            if node in chain:
                raise ValueError(f"Cycle in SWC parent references at node {node}.")
            chain.add(node)
            node = links[node]
        done.update(chain)


def parse_swc(text: str, *, source_units: Literal["nm", "um"]) -> Skeleton:
    if source_units not in {"nm", "um"}:
        raise ValueError("SWC units must be specified explicitly as nm or um.")
    scale = 1.0 if source_units == "nm" else 1000.0
    nodes = []
    for number, line in enumerate(text.splitlines(), 1):
        fields = line.split("#", 1)[0].strip().split()
        if not fields:
            continue
        if len(fields) != 7:
            raise ValueError(f"SWC line {number}: expected 7 columns, found {len(fields)}.")
        try:
            node_id, label, parent = int(fields[0]), int(fields[1]), int(fields[6])
            values = [float(x) * scale for x in fields[2:6]]
        except ValueError as exc:
            raise ValueError(f"SWC line {number}: invalid numeric value.") from exc
        if node_id < 0 or label < 0 or parent < -1:
            raise ValueError(f"SWC line {number}: invalid node ID, label or parent.")
        if not all(math.isfinite(v) for v in values) or values[3] < 0:
            raise ValueError(f"SWC line {number}: coordinates/radius must be finite; radius >= 0.")
        nodes.append(
            SkeletonNode(
                node_id, label, tuple(values[:3]), values[3], None if parent == -1 else parent
            )
        )
    validate_parents([n.id for n in nodes], [n.parent_id for n in nodes])
    return Skeleton(tuple(nodes), source_units)


def read_swc(path: Path, *, source_units: Literal["nm", "um"]) -> Skeleton:
    return parse_swc(path.read_text(encoding="utf-8-sig"), source_units=source_units)
