"""Replaceable temporary drawing geometry and deterministic simulation routing."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import heapq
import json
import math
from pathlib import Path


DEFAULT_MAP = Path(__file__).resolve().parent / "data" / "little-town-temporary.json"


class MapDefinition:
    """Drawing facts only: no robot transform, physical car pose, or motion target."""

    def __init__(self, path: str | Path | None = None):
        self._data = json.loads(Path(path or DEFAULT_MAP).read_text(encoding="utf-8-sig"))
        self._validate()
        self.id = self._data["id"]
        self.version = self._data["version"]
        self._nodes = {node["id"]: node for node in self._data["nodes"]}
        geometry = {key: self._data[key] for key in (
            "board", "page", "start", "destinations", "markers", "marker_dictionary", "building_panels")}
        geometry["nodes"] = sorted(self._data["nodes"], key=lambda node: node["id"])
        geometry["edges"] = sorted(self._data["edges"], key=lambda edge: (edge["from"], edge["to"]))
        geometry["destinations"] = sorted(geometry["destinations"])
        geometry["markers"] = sorted(geometry["markers"], key=lambda marker: marker["id"])
        geometry["building_panels"] = sorted(geometry["building_panels"], key=lambda panel: panel["id"])
        self.geometry_hash = hashlib.sha256(json.dumps(geometry, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
        self._adjacency: dict[str, list[tuple[str, float]]] = {node: [] for node in self._nodes}
        for edge in self._data["edges"]:
            self._adjacency[edge["from"]].append((edge["to"], edge["length_mm"]))
            if edge["bidirectional"]:
                self._adjacency[edge["to"]].append((edge["from"], edge["length_mm"]))

    @property
    def data(self) -> dict:
        return deepcopy(self._data)

    @staticmethod
    def _finite(value) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)

    def _validate(self) -> None:
        data = self._data
        if data.get("schema_version") != "pushpilot.temporary-map.v1" or data.get("temporary") is not True or data.get("physical_execution_enabled") is not False:
            raise ValueError("Only explicitly temporary, non-executing maps are supported.")
        if not all(isinstance(data.get(key), str) and data[key] for key in ("id", "version", "title", "start", "marker_dictionary")):
            raise ValueError("Map identity is incomplete.")
        if data["marker_dictionary"] != "DICT_4X4_50":
            raise ValueError("Temporary-map image detection supports only DICT_4X4_50 markers.")
        board = data.get("board", {})
        if not all(self._finite(board.get(key)) and board[key] > 0 for key in ("width_mm", "height_mm", "road_width_mm", "junction_size_mm")):
            raise ValueError("Map board dimensions must be finite and positive.")
        nodes = data.get("nodes", [])
        if not isinstance(nodes, list) or not 2 <= len(nodes) <= 500:
            raise ValueError("Map node count is invalid.")
        identifiers = []
        for node in nodes:
            if not isinstance(node.get("id"), str) or not node["id"] or node.get("kind") not in {"junction", "destination"}:
                raise ValueError("Map nodes need unique identities and supported kinds.")
            if not all(self._finite(node.get(axis)) for axis in ("x_mm", "y_mm")):
                raise ValueError("Node coordinates must be finite.")
            if not 0 <= node["x_mm"] <= board["width_mm"] or not 0 <= node["y_mm"] <= board["height_mm"]:
                raise ValueError("Node coordinates lie outside the working board.")
            identifiers.append(node["id"])
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("Map node identities must be unique.")
        by_id = {node["id"]: node for node in nodes}
        destinations = data.get("destinations")
        if (not isinstance(destinations, list) or not destinations or len(destinations) != len(set(destinations))
                or data["start"] not in by_id or any(item not in by_id or item == data["start"] for item in destinations)):
            raise ValueError("Map start or destinations are invalid.")
        seen_edges = set()
        for edge in data.get("edges", []):
            first, second = edge.get("from"), edge.get("to")
            if first not in by_id or second not in by_id or first == second or type(edge.get("bidirectional")) is not bool:
                raise ValueError("Map edge endpoints or direction are invalid.")
            length = edge.get("length_mm")
            a, b = by_id[first], by_id[second]
            dx, dy = abs(a["x_mm"] - b["x_mm"]), abs(a["y_mm"] - b["y_mm"])
            if not self._finite(length) or length <= 0 or (dx > 0 and dy > 0) or not math.isclose(length, dx + dy, abs_tol=1e-6):
                raise ValueError("Edges must have accurate positive cardinal drawing lengths.")
            identity = tuple(sorted((first, second))) if edge["bidirectional"] else (first, second)
            if identity in seen_edges:
                raise ValueError("Duplicate map edges are unsupported.")
            seen_edges.add(identity)
        marker_ids = []
        for marker in data.get("markers", []):
            center = marker.get("center_mm", [])
            if (type(marker.get("id")) is not int or not 0 <= marker["id"] < 50 or len(center) != 2
                    or not all(self._finite(value) for value in center)
                    or not self._finite(marker.get("size_mm")) or marker["size_mm"] <= 0):
                raise ValueError("Marker geometry is invalid.")
            marker_ids.append(marker["id"])
        if len(marker_ids) != len(set(marker_ids)) or len(marker_ids) < 4:
            raise ValueError("At least four uniquely identified map markers are required.")
        if not isinstance(data.get("page"), dict) or not isinstance(data.get("building_panels"), list):
            raise ValueError("Print layout facts are required.")

    def snapshot(self) -> dict:
        public = {key: deepcopy(self._data[key]) for key in (
            "schema_version", "id", "version", "title", "temporary", "physical_execution_enabled",
            "board", "start", "destinations", "nodes", "edges", "markers", "building_panels", "limitations")}
        return {**public, "geometry_hash": self.geometry_hash}

    def route(self, destination: str) -> dict:
        if destination not in self._data["destinations"]:
            raise ValueError("Select a supported destination from the temporary map.")
        start = self._data["start"]
        # The prototype starts facing east. The first edge must follow that heading.
        queue = [(0.0, (start,), start)]
        best: dict[str, tuple[float, tuple[str, ...]]] = {}
        while queue:
            distance, path, current = heapq.heappop(queue)
            if current in best and best[current] <= (distance, path):
                continue
            best[current] = (distance, path)
            if current == destination:
                points = [[self._nodes[node]["x_mm"], self._nodes[node]["y_mm"]] for node in path]
                return {"map_id": self.id, "map_version": self.version, "map_hash": self.geometry_hash,
                        "temporary": True, "physical_execution_enabled": False,
                        "start": start, "destination": destination, "node_ids": list(path), "points_mm": points,
                        "distance_mm": distance,
                        "junction_ids": [node for node in path[1:-1] if self._nodes[node]["kind"] == "junction"]}
            for neighbor, length in sorted(self._adjacency[current]):
                if neighbor in path:
                    continue
                if current == start:
                    first, second = self._nodes[start], self._nodes[neighbor]
                    if second["x_mm"] <= first["x_mm"] or second["y_mm"] != first["y_mm"]:
                        continue
                heapq.heappush(queue, (distance + length, (*path, neighbor), neighbor))
        raise ValueError("No east-facing route reaches this destination on the temporary map.")
