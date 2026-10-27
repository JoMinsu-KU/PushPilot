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
        # Labels and language aliases are display metadata, not calibration facts.
        geometry["nodes"] = [{key: node[key] for key in ("id", "x_mm", "y_mm", "kind")}
                             for node in geometry["nodes"]]
        if self.start_heading != "east":
            geometry["start_heading"] = self.start_heading
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

    @property
    def start_heading(self) -> str:
        return self._data.get("start_heading", "east")

    def node_label(self, identifier: str) -> str:
        return self._nodes[identifier].get("label", identifier)

    def goal_context(self) -> dict:
        """Symbolic language metadata only; never send map coordinates to MUSE."""
        def place(identifier):
            return {"id": identifier, "label": self.node_label(identifier),
                    "aliases": deepcopy(self._nodes[identifier].get("aliases", []))}
        return {"start": place(self._data["start"]),
                "destinations": [place(identifier) for identifier in self._data["destinations"]]}

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
        if data.get("start_heading", "east") not in {"east", "south", "west", "north"}:
            raise ValueError("Map start heading must be east, south, west, or north.")
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
            if ("label" in node and (not isinstance(node["label"], str) or not 1 <= len(node["label"]) <= 100)):
                raise ValueError("Node labels must be nonempty display strings of at most 100 characters.")
            aliases = node.get("aliases", [])
            if (not isinstance(aliases, list) or len(aliases) > 20
                    or any(not isinstance(alias, str) or not 1 <= len(alias) <= 100 for alias in aliases)):
                raise ValueError("Node aliases must be a bounded list of nonempty strings.")
            identifiers.append(node["id"])
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("Map node identities must be unique.")
        by_id = {node["id"]: node for node in nodes}
        destinations = data.get("destinations")
        if (not isinstance(destinations, list) or not destinations or len(destinations) != len(set(destinations))
                or data["start"] not in by_id or any(item not in by_id or item in {data["start"], "UNKNOWN"} for item in destinations)):
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
        return {**public, "start_heading": self.start_heading, "geometry_hash": self.geometry_hash}

    def route(self, destination: str) -> dict:
        if destination not in self._data["destinations"]:
            raise ValueError("Select a supported destination from the temporary map.")
        start = self._data["start"]
        # Heading is map configuration, independent of robot/tool orientation.
        queue = [(0.0, (start,), start)]
        best: dict[str, tuple[float, tuple[str, ...]]] = {}
        while queue:
            distance, path, current = heapq.heappop(queue)
            if current in best and best[current] <= (distance, path):
                continue
            best[current] = (distance, path)
            if current == destination:
                points = [[self._nodes[node]["x_mm"], self._nodes[node]["y_mm"]] for node in path]
                route = {"map_id": self.id, "map_version": self.version, "map_hash": self.geometry_hash,
                        "temporary": True, "physical_execution_enabled": False,
                        "start": start, "destination": destination, "node_ids": list(path), "points_mm": points,
                        "distance_mm": distance,
                        "junction_ids": [node for node in path[1:-1] if self._nodes[node]["kind"] == "junction"]}
                route["visualization"] = self._visualization(route)
                return route
            for neighbor, length in sorted(self._adjacency[current]):
                if neighbor in path:
                    continue
                if current == start:
                    first, second = self._nodes[start], self._nodes[neighbor]
                    dx, dy = second["x_mm"] - first["x_mm"], second["y_mm"] - first["y_mm"]
                    heading = ("east" if dx > 0 else "west") if dx else ("south" if dy > 0 else "north")
                    if heading != self.start_heading:
                        continue
                heapq.heappush(queue, (distance + length, (*path, neighbor), neighbor))
        raise ValueError(f"No {self.start_heading}-facing route reaches this destination on the temporary map.")

    def _visualization(self, route: dict) -> dict:
        """Split drawing centerlines for status display, not physical stop targets.

        Neighboring junction offsets occupy at most half of each shared edge.
        This permits touching display regions on very short roads without
        reversing a segment or changing the supervisor's bounded action count.
        """
        points, nodes = route["points_mm"], route["node_ids"]
        identity = {key: route[key] for key in ("map_id", "map_version", "map_hash", "node_ids")}
        prefix = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:20]
        junctions, segments = [], []
        by_index = {}
        for index in range(1, len(nodes) - 1):
            if nodes[index] not in route["junction_ids"]:
                continue
            before, center, after = points[index - 1:index + 2]
            incoming = math.dist(before, center)
            outgoing = math.dist(center, after)
            incoming_unit = [(center[axis] - before[axis]) / incoming for axis in (0, 1)]
            outgoing_unit = [(after[axis] - center[axis]) / outgoing for axis in (0, 1)]
            stop_offset = min(self._data["board"]["junction_size_mm"] / 2, incoming / 2)
            exit_offset = min(self._data["board"]["junction_size_mm"] / 2, outgoing / 2)
            stop = [center[axis] - incoming_unit[axis] * stop_offset for axis in (0, 1)]
            exit_point = [center[axis] + outgoing_unit[axis] * exit_offset for axis in (0, 1)]
            half_width = self._data["board"]["road_width_mm"] / 2
            perpendicular = [-incoming_unit[1] * half_width, incoming_unit[0] * half_width]
            junction = {"node_id": nodes[index], "label": self.node_label(nodes[index]),
                        "center_mm": center, "stop_point_mm": stop,
                        "stop_line_mm": [[stop[axis] + sign * perpendicular[axis] for axis in (0, 1)] for sign in (-1, 1)],
                        "exit_point_mm": exit_point,
                        "approach_segment_id": f"route-{prefix}-push-{index}",
                        "crossing_segment_id": f"route-{prefix}-crossing-{index}"}
            junctions.append(junction)
            by_index[index] = junction
        for index in range(1, len(nodes)):
            first = by_index[index - 1]["exit_point_mm"] if index - 1 in by_index else points[index - 1]
            last = by_index[index]["stop_point_mm"] if index in by_index else points[index]
            segments.append({"id": f"route-{prefix}-push-{index}", "kind": "push",
                             "from_node_id": nodes[index - 1], "to_node_id": nodes[index],
                             "junction_id": nodes[index] if index in by_index else None,
                             "points_mm": [first, last], "length_mm": math.dist(first, last)})
            if index in by_index:
                junction = by_index[index]
                crossing = [junction["stop_point_mm"], points[index], junction["exit_point_mm"]]
                segments.append({"id": junction["crossing_segment_id"], "kind": "crossing",
                                 "from_node_id": nodes[index - 1], "to_node_id": nodes[index + 1],
                                 "junction_id": nodes[index], "points_mm": crossing,
                                 "length_mm": sum(math.dist(a, b) for a, b in zip(crossing, crossing[1:]))})
        return {"schema_version": "pushpilot.route-display.v1", "source": "drawing_only",
                "segments": segments, "junctions": junctions}
