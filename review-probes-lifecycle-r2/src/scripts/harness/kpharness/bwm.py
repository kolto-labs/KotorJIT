"""Small, bounded reader for KotOR BWM/WOK walkmeshes.

Only the header, vertices, face indices, and walkable-face adjacency are
needed by the harness.  Rejecting an odd file is preferable to guessing a
route from it.
"""
from __future__ import annotations

import math
import struct
from collections import deque
from dataclasses import dataclass
from typing import Iterable


class BwmError(ValueError):
    pass


@dataclass(frozen=True)
class Face:
    vertices: tuple[int, int, int]
    centroid: tuple[float, float, float]


@dataclass(frozen=True)
class Bwm:
    vertices: tuple[tuple[float, float, float], ...]
    faces: tuple[Face, ...]
    walkable_count: int

    @property
    def walkable_faces(self) -> range:
        return range(self.walkable_count)


def _range(size: int, offset: int, count: int, stride: int, name: str) -> None:
    if offset < 0 or count < 0 or offset > size or stride <= 0 or count > (size - offset) // stride:
        raise BwmError(f"{name} range is outside file")


def parse(data: bytes, *, max_vertices: int = 1_000_000, max_faces: int = 1_000_000) -> Bwm:
    """Parse documented BWM V1.0 geometry with checked byte ranges."""
    if len(data) < 136:
        raise BwmError("truncated BWM header")
    if data[:8] != b"BWM V1.0":
        raise BwmError("expected BWM V1.0")
    fields = struct.unpack_from("<16I", data, 72)
    vertices_count, vertices_offset, faces_count, indices_offset = fields[:4]
    # The documented header stores the count of walkable faces beside the
    # adjacency table; retail writers order these faces first.
    walkable_count, adjacency_offset = fields[10:12]
    if vertices_count > max_vertices or faces_count > max_faces:
        raise BwmError("BWM count exceeds harness limit")
    if walkable_count > faces_count:
        raise BwmError("walkable-face count exceeds face count")
    _range(len(data), vertices_offset, vertices_count, 12, "vertices")
    _range(len(data), indices_offset, faces_count, 12, "face indices")
    _range(len(data), adjacency_offset, walkable_count, 12, "walkable adjacency")
    vertices = tuple(struct.unpack_from("<3f", data, vertices_offset + i * 12)
                     for i in range(vertices_count))
    if any(not math.isfinite(x) for point in vertices for x in point):
        raise BwmError("non-finite vertex")
    faces: list[Face] = []
    for i in range(faces_count):
        tri = struct.unpack_from("<3I", data, indices_offset + i * 12)
        if any(index >= vertices_count for index in tri):
            raise BwmError(f"face {i} references a missing vertex")
        points = [vertices[index] for index in tri]
        centroid = tuple(sum(point[axis] for point in points) / 3.0 for axis in range(3))
        faces.append(Face(tri, centroid))
    return Bwm(vertices, tuple(faces), walkable_count)


def _graph(mesh: Bwm) -> dict[int, set[int]]:
    """Build only shared-edge links among BWM's declared walkable prefix."""
    edge_owner: dict[tuple[int, int], int] = {}
    graph = {i: set() for i in mesh.walkable_faces}
    for i in mesh.walkable_faces:
        a, b, c = mesh.faces[i].vertices
        for left, right in ((a, b), (b, c), (c, a)):
            edge = tuple(sorted((left, right)))
            other = edge_owner.get(edge)
            if other is None:
                edge_owner[edge] = i
            else:
                graph[i].add(other)
                graph[other].add(i)
    return graph


def select_far_side(mesh: Bwm, *, door: Iterable[float], approach: Iterable[float],
                    normal_xy: Iterable[float], min_projection: float = 0.5) -> dict[str, object]:
    """Return a connected walkable centroid on the opposite side of a door plane.

    The caller supplies the authored door normal and measured approach point;
    this function never infers either from a screenshot or a model axis.
    """
    door = tuple(float(x) for x in door)
    approach = tuple(float(x) for x in approach)
    normal = tuple(float(x) for x in normal_xy)
    if len(door) != 3 or len(approach) != 3 or len(normal) != 2 or not all(math.isfinite(x) for x in (*door, *approach, *normal)):
        raise BwmError("door, approach, and normal must be finite coordinates")
    length = math.hypot(*normal)
    if length == 0 or not math.isfinite(min_projection) or min_projection <= 0:
        raise BwmError("normal and minimum projection must be positive")
    normal = (normal[0] / length, normal[1] / length)
    projection = lambda p: (p[0] - door[0]) * normal[0] + (p[1] - door[1]) * normal[1]
    approach_projection = projection(approach)
    if approach_projection >= -min_projection:
        raise BwmError("approach is not provably on the declared near side")
    near = min(mesh.walkable_faces, key=lambda i: math.dist(mesh.faces[i].centroid, approach))
    graph = _graph(mesh)
    queue, parent = deque([near]), {near: None}
    while queue:
        current = queue.popleft()
        for child in graph[current]:
            if child not in parent:
                parent[child] = current
                queue.append(child)
    candidates = [i for i in parent if projection(mesh.faces[i].centroid) >= min_projection]
    if not candidates:
        raise BwmError("no connected walkable face on declared far side")
    chosen = min(candidates, key=lambda i: (len(_path(parent, i)), math.dist(mesh.faces[i].centroid, door)))
    return {"face": chosen, "centroid": list(mesh.faces[chosen].centroid),
            "path": _path(parent, chosen), "near_face": near,
            "approach_projection": approach_projection,
            "far_projection": projection(mesh.faces[chosen].centroid)}


def _path(parent: dict[int, int | None], end: int) -> list[int]:
    out: list[int] = []
    while end is not None:
        out.append(end)
        end = parent[end]
    return list(reversed(out))
