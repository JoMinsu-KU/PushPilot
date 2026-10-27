"""Replaceable temporary drawing geometry and deterministic simulation routing."""
from __future__ import annotations

from collections import deque
from copy import deepcopy
import hashlib
import heapq
import json
import math
from pathlib import Path


DEFAULT_MAP = Path(__file__).resolve().parent / "data" / "little-town-temporary.json"
MAX_ROUTE_NODES = 64


class MapDefinition:
    """Drawing facts only: no robot transform, physical car pose, or motion target."""

    def __init__(self, path: str | Path | None = None, *, data: dict | None = None):
        if data is not None:
            if path is not None or not isinstance(data, dict):
                raise ValueError("Supply either a map file or a map definition object.")
            self._data = deepcopy(data)
        else:
            self._data = json.loads(Path(path or DEFAULT_MAP).read_text(encoding="utf-8-sig"))
        if not isinstance(self._data, dict):
            raise ValueError("The map definition must be a JSON object.")
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
        if not self.camera_registration_supported:
            geometry["camera_registration_supported"] = False
        geometry["edges"] = sorted(self._data["edges"], key=lambda edge: (edge["from"], edge["to"]))
        geometry["destinations"] = sorted(geometry["destinations"])
        geometry["markers"] = sorted(geometry["markers"], key=lambda marker: marker["id"])
        geometry["building_panels"] = sorted(geometry["building_panels"], key=lambda panel: panel["id"])
        if self._data.get("signal_targets"):
            geometry["signal_targets"] = sorted(self._data["signal_targets"], key=lambda target: target["id"])
        self.geometry_hash = hashlib.sha256(json.dumps(geometry, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
        self._adjacency: dict[str, list[tuple[str, float]]] = {node: [] for node in self._nodes}
        for edge in self._data["edges"]:
            self._adjacency[edge["from"]].append((edge["to"], edge["length_mm"]))
            if edge["bidirectional"]:
                self._adjacency[edge["to"]].append((edge["from"], edge["length_mm"]))

    @classmethod
    def from_data(cls, data: dict) -> MapDefinition:
        """Validate an isolated in-memory definition without reading a map file."""
        if not isinstance(data, dict):
            raise ValueError("The map definition must be a JSON object.")
        return cls(data=data)

    @property
    def data(self) -> dict:
        return deepcopy(self._data)

    @property
    def start_heading(self) -> str:
        return self._data.get("start_heading", "east")

    @property
    def camera_registration_supported(self) -> bool:
        return self._data.get("camera_registration_supported", True)

    def node_label(self, identifier: str) -> str:
        return self._nodes[identifier].get("label", identifier)

    def goal_context(self) -> dict:
        """Symbolic language metadata only; never send map coordinates to MUSE."""
        def place(identifier):
            return {"id": identifier, "label": self.node_label(identifier),
                    "aliases": deepcopy(self._nodes[identifier].get("aliases", []))}
        return {"start": place(self._data["start"]),
                "destinations": [place(identifier) for identifier in self._data["destinations"]]}

    def planning_context(self) -> dict:
        """Ground model choices in symbolic drawing topology, never robot targets.

        Rows and columns are nonmetric ordering ranks in the printed map frame.
        The configured start is a scenario declaration, not an observed car pose.
        Both directions of each bidirectional road are explicitly enumerated.
        """
        columns = {value: index for index, value in enumerate(sorted({node["x_mm"] for node in self._nodes.values()}))}
        rows = {value: index for index, value in enumerate(sorted({node["y_mm"] for node in self._nodes.values()}))}
        nodes = [{"id": identifier, "label": self.node_label(identifier),
                  "aliases": deepcopy(node.get("aliases", [])), "kind": node["kind"],
                  "drawing_position": {"column": columns[node["x_mm"]], "row": rows[node["y_mm"]]}}
                 for identifier, node in sorted(self._nodes.items())]
        edges = [{"from": first, "to": second, "map_direction": self._edge_direction(first, second)}
                 for first, neighbors in sorted(self._adjacency.items()) for second, _length in sorted(neighbors)]
        return {"schema_version": "pushpilot.planning-graph.v1", "source": "drawing_only",
                "map_id": self.id, "map_version": self.version, "map_hash": self.geometry_hash,
                "camera_registration_supported": self.camera_registration_supported,
                "physical_execution_enabled": False,
                "orientation": {"north": "map_up", "east": "map_right", "south": "map_down", "west": "map_left",
                                "turn_reference": "incoming_path_direction", "position_units": "nonmetric_ordering_ranks"},
                "declared_start": {"node_id": self._data["start"], "configured_heading": self.start_heading,
                                   "source": "map_configuration", "measured_pose": False,
                                   "departure_restricted_to_configured_heading": False},
                "destinations": deepcopy(self._data["destinations"]), "nodes": nodes, "directed_edges": edges,
                "max_route_nodes": MAX_ROUTE_NODES,
                "rules": ["Select a simple connected directed path with no repeated nodes.",
                          "Start at declared_start.node_id and finish at the selected destination.",
                          "Include every intermediate graph node; do not jump across roads or omit a place on a road.",
                          "Stop before every junction and inspect a fresh signal image while stopped.",
                          "An image does not establish measured car pose or authorize physical execution."]}

    def _edge_direction(self, first: str, second: str) -> str:
        a, b = self._nodes[first], self._nodes[second]
        dx, dy = b["x_mm"] - a["x_mm"], b["y_mm"] - a["y_mm"]
        return ("east" if dx > 0 else "west") if dx else ("south" if dy > 0 else "north")

    def route_from_nodes(self, destination: str, node_ids: list[str]) -> dict:
        """Compile exactly the selected graph path without choosing a substitute.

        Unlike the legacy demo router, this permits any registered departure.
        It does not establish that a physical car can follow the drawing path.
        """
        if not isinstance(destination, str) or destination not in self._data["destinations"]:
            raise ValueError("Select a supported destination from the temporary map.")
        if (not isinstance(node_ids, list) or not 2 <= len(node_ids) <= min(MAX_ROUTE_NODES, len(self._nodes))
                or any(not isinstance(node, str) or node not in self._nodes for node in node_ids)):
            raise ValueError("The selected route must be a bounded list of known map node identities.")
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("The selected route must not repeat nodes or contain cycles.")
        if node_ids[0] != self._data["start"] or node_ids[-1] != destination:
            raise ValueError("The selected route must match the declared start and finish at its destination.")
        distance = 0.0
        for first, second in zip(node_ids, node_ids[1:]):
            edge = next((length for neighbor, length in self._adjacency[first] if neighbor == second), None)
            if edge is None:
                raise ValueError("The selected route contains an unavailable directed road.")
            distance += edge
        route = {"map_id": self.id, "map_version": self.version, "map_hash": self.geometry_hash,
                 "temporary": True, "physical_execution_enabled": False,
                 "start": self._data["start"], "destination": destination, "node_ids": list(node_ids),
                 "points_mm": [[self._nodes[node]["x_mm"], self._nodes[node]["y_mm"]] for node in node_ids],
                 "distance_mm": distance,
                 "junction_ids": [node for node in node_ids[1:-1] if self._nodes[node]["kind"] == "junction"]}
        route["visualization"] = self._visualization(route)
        route["directions"] = self._directions(route)
        return route

    def _directions(self, route: dict) -> dict:
        """Derive maneuver semantics only from the validated drawing path."""
        nodes = route["node_ids"]
        headings = [self._edge_direction(first, second) for first, second in zip(nodes, nodes[1:])]
        compass = {"north": 0, "east": 1, "south": 2, "west": 3}
        maneuvers = []
        for index, node in enumerate(nodes[1:-1], 1):
            if node not in route["junction_ids"]:
                continue
            delta = (compass[headings[index]] - compass[headings[index - 1]]) % 4
            turn = {0: "straight", 1: "right", 2: "u_turn", 3: "left"}[delta]
            description = (f"Continue straight at {self.node_label(node)}." if turn == "straight" else
                           f"Make a U-turn at {self.node_label(node)}." if turn == "u_turn" else
                           f"Turn {turn} at {self.node_label(node)}.")
            maneuvers.append({"node_id": node, "incoming_node_id": nodes[index - 1],
                              "outgoing_node_id": nodes[index + 1], "incoming_direction": headings[index - 1],
                              "outgoing_direction": headings[index], "turn": turn, "requires_stop": True,
                              "description": description})
        return {"schema_version": "pushpilot.route-directions.v1", "source": "drawing_only",
                "departure": {"from_node_id": nodes[0], "to_node_id": nodes[1], "map_direction": headings[0],
                              "description": f"Follow the road from {self.node_label(nodes[0])} toward {self.node_label(nodes[1])}."},
                "maneuvers": maneuvers,
                "arrival": {"node_id": nodes[-1], "description": f"Stop at {self.node_label(nodes[-1])} and verify the destination."}}

    def validate_route_constraints(self, route: dict, constraints: dict) -> dict:
        """Reject a selected route that violates its declared interpretation.

        The first-turn condition refers to the first junction encountered,
        including a straight continuation. Via nodes must appear in order.
        This checks the structured interpretation, not natural-language truth.
        """
        if not isinstance(route, dict) or any(route.get(key) != value for key, value in (
                ("map_id", self.id), ("map_version", self.version), ("map_hash", self.geometry_hash))):
            raise ValueError("The selected route belongs to a different map identity or geometry.")
        canonical = self.route_from_nodes(route.get("destination"), route.get("node_ids"))
        if not isinstance(constraints, dict) or set(constraints) != {"departure", "first_turn", "via_nodes", "avoid_nodes"}:
            raise ValueError("Route constraints need departure, first_turn, via_nodes, and avoid_nodes only.")
        departure, first_turn = constraints["departure"], constraints["first_turn"]
        if not isinstance(departure, str) or departure not in {"any", "north", "east", "south", "west"}:
            raise ValueError("The declared departure direction is unsupported.")
        if not isinstance(first_turn, str) or first_turn not in {"any", "left", "right", "straight"}:
            raise ValueError("The declared first-junction maneuver is unsupported.")
        for key in ("via_nodes", "avoid_nodes"):
            values = constraints[key]
            if (not isinstance(values, list) or len(values) > min(MAX_ROUTE_NODES, len(self._nodes))
                    or any(not isinstance(value, str) or value not in self._nodes for value in values)
                    or len(values) != len(set(values))):
                raise ValueError("Via and avoided nodes must be bounded lists of distinct map identities.")
        if set(constraints["via_nodes"]) & set(constraints["avoid_nodes"]):
            raise ValueError("A route cannot both visit and avoid the same node.")
        directions = canonical["directions"]
        if departure != "any" and departure != directions["departure"]["map_direction"]:
            raise ValueError("The selected route violates its declared departure direction.")
        maneuvers = directions["maneuvers"]
        if first_turn != "any" and (not maneuvers or maneuvers[0]["turn"] != first_turn):
            raise ValueError("The selected route violates its declared first-junction maneuver.")
        nodes = canonical["node_ids"]
        if any(node in nodes for node in constraints["avoid_nodes"]):
            raise ValueError("The selected route includes a declared avoided node.")
        positions = [nodes.index(node) if node in nodes else -1 for node in constraints["via_nodes"]]
        if any(position < 0 for position in positions) or positions != sorted(positions):
            raise ValueError("The selected route does not visit every declared via node in order.")
        return deepcopy(constraints)

    def signal_target(self, junction_id: str, approach_from: str) -> dict | None:
        """Return an explicitly configured approach-specific drawing region.

        No region is inferred from marker, junction, or road geometry. Missing
        metadata must not be treated as a usable signal observation target.
        """
        for target in self._data.get("signal_targets", []):
            if target["junction_id"] == junction_id and target["approach_from"] == approach_from:
                return deepcopy(target)
        return None

    def planning_audit(self) -> dict:
        """Check bounded directed reachability without running an installation."""
        start = self._data["start"]
        shortest_nodes = {start: 1}
        queue = deque([start])
        while queue:
            current = queue.popleft()
            for neighbor, _length in self._adjacency[current]:
                if neighbor not in shortest_nodes:
                    shortest_nodes[neighbor] = shortest_nodes[current] + 1
                    queue.append(neighbor)
        unavailable = [node for node in self._data["destinations"]
                       if shortest_nodes.get(node, MAX_ROUTE_NODES + 1) > MAX_ROUTE_NODES]
        return {"status": "failed" if unavailable else "passed", "source": "drawing_only",
                "map_id": self.id, "map_version": self.version, "map_hash": self.geometry_hash,
                "camera_registration_supported": self.camera_registration_supported,
                "node_count": len(self._nodes), "directed_edge_count": sum(len(edges) for edges in self._adjacency.values()),
                "declared_start": start, "max_route_nodes": MAX_ROUTE_NODES,
                "destinations": deepcopy(self._data["destinations"]), "unreachable_within_route_limit": unavailable,
                "configured_signal_target_count": len(self._data.get("signal_targets", [])),
                "equipment_contacted": False, "physical_execution_enabled": False,
                "limitations": ["Reachability does not qualify car contact, turns, stopping, or camera registration.",
                                "Absent signal targets remain unavailable; this audit invents no signal regions."]}

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
        if type(data.get("camera_registration_supported", True)) is not bool:
            raise ValueError("Camera registration support must be explicitly true or false.")
        board = data.get("board", {})
        if not isinstance(board, dict) or not all(self._finite(board.get(key)) and board[key] > 0 for key in ("width_mm", "height_mm", "road_width_mm", "junction_size_mm")):
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
        edges = data.get("edges")
        if not isinstance(edges, list) or len(edges) > 2000:
            raise ValueError("Map edges must be a list of at most 2000 directed or bidirectional roads.")
        seen_edges = set()
        for edge in edges:
            first, second = edge.get("from"), edge.get("to")
            if first not in by_id or second not in by_id or first == second or type(edge.get("bidirectional")) is not bool:
                raise ValueError("Map edge endpoints or direction are invalid.")
            length = edge.get("length_mm")
            a, b = by_id[first], by_id[second]
            dx, dy = abs(a["x_mm"] - b["x_mm"]), abs(a["y_mm"] - b["y_mm"])
            if not self._finite(length) or length <= 0 or (dx > 0 and dy > 0) or not math.isclose(length, dx + dy, abs_tol=1e-6):
                raise ValueError("Edges must have accurate positive cardinal drawing lengths.")
            identities = {(first, second), (second, first)} if edge["bidirectional"] else {(first, second)}
            if identities & seen_edges:
                raise ValueError("Duplicate map edges are unsupported.")
            seen_edges.update(identities)
        markers = data.get("markers")
        if not isinstance(markers, list) or len(markers) > 50:
            raise ValueError("Map markers must be a list of at most 50 declared marker regions.")
        marker_ids = []
        for marker in markers:
            center = marker.get("center_mm", [])
            if (type(marker.get("id")) is not int or not 0 <= marker["id"] < 50 or len(center) != 2
                    or not all(self._finite(value) for value in center)
                    or not self._finite(marker.get("size_mm")) or marker["size_mm"] <= 0):
                raise ValueError("Marker geometry is invalid.")
            marker_ids.append(marker["id"])
        if len(marker_ids) != len(set(marker_ids)):
            raise ValueError("Declared map marker identities must be unique.")
        if self.camera_registration_supported and len(marker_ids) < 4:
            raise ValueError("At least four uniquely identified map markers are required for camera registration.")
        page = data.get("page")
        if not isinstance(page, dict) or not all(self._finite(page.get(key)) and page[key] > 0 for key in ("width_mm", "height_mm")):
            raise ValueError("Print page dimensions must be finite and positive.")
        origin = page.get("board_origin_page_mm")
        if (not isinstance(origin, list) or len(origin) != 2 or not all(self._finite(value) and value >= 0 for value in origin)
                or origin[0] + board["width_mm"] > page["width_mm"]
                or origin[1] + board["height_mm"] > page["height_mm"]):
            raise ValueError("The working board must fit inside the declared print page.")
        panels = data.get("building_panels")
        if not isinstance(panels, list) or len(panels) > 500:
            raise ValueError("Building panels must be a list of at most 500 drawing regions.")
        panel_ids = set()
        for panel in panels:
            if (not isinstance(panel, dict) or not isinstance(panel.get("id"), str) or not 1 <= len(panel["id"]) <= 100
                    or panel["id"] in panel_ids):
                raise ValueError("Building panels need bounded unique identities.")
            bounds = panel.get("bounds_mm")
            if (not isinstance(bounds, list) or len(bounds) != 4 or not all(self._finite(value) for value in bounds)
                    or not 0 <= bounds[0] < bounds[2] <= board["width_mm"]
                    or not 0 <= bounds[1] < bounds[3] <= board["height_mm"]):
                raise ValueError("Building panel bounds must be positive drawing rectangles inside the board.")
            panel_ids.add(panel["id"])
        limitations = data.get("limitations")
        if (not isinstance(limitations, list) or len(limitations) > 100
                or any(not isinstance(value, str) or not 1 <= len(value) <= 1000 for value in limitations)):
            raise ValueError("Map limitations must be a bounded list of nonempty strings.")
        targets = data.get("signal_targets", [])
        if not isinstance(targets, list) or len(targets) > 500:
            raise ValueError("Signal targets must be a bounded list of reviewed approach-specific regions.")
        target_ids, approaches = set(), set()
        directed = {(edge["from"], edge["to"]) for edge in data.get("edges", [])}
        directed.update((edge["to"], edge["from"]) for edge in data.get("edges", []) if edge["bidirectional"])
        for target in targets:
            if (not isinstance(target, dict) or set(target) != {"id", "junction_id", "approach_from", "bounds_mm", "description"}
                    or not isinstance(target["id"], str) or not 1 <= len(target["id"]) <= 100
                    or not isinstance(target["junction_id"], str) or target["junction_id"] not in by_id
                    or by_id[target["junction_id"]]["kind"] != "junction"
                    or not isinstance(target["approach_from"], str) or target["approach_from"] not in by_id
                    or (target["approach_from"], target["junction_id"]) not in directed
                    or not isinstance(target["description"], str) or not 1 <= len(target["description"]) <= 500):
                raise ValueError("A signal target needs a unique identity, valid incoming road, and bounded description.")
            bounds = target["bounds_mm"]
            if (not isinstance(bounds, list) or len(bounds) != 4 or not all(self._finite(value) for value in bounds)
                    or not 0 <= bounds[0] < bounds[2] <= board["width_mm"]
                    or not 0 <= bounds[1] < bounds[3] <= board["height_mm"]):
                raise ValueError("Signal target bounds must be a positive drawing rectangle inside the board.")
            approach = (target["junction_id"], target["approach_from"])
            if target["id"] in target_ids or approach in approaches:
                raise ValueError("Signal target identities and junction approaches must be unique.")
            target_ids.add(target["id"])
            approaches.add(approach)

    def snapshot(self) -> dict:
        public = {key: deepcopy(self._data[key]) for key in (
            "schema_version", "id", "version", "title", "temporary", "physical_execution_enabled",
            "board", "start", "destinations", "nodes", "edges", "markers", "building_panels", "limitations")}
        return {**public, "start_heading": self.start_heading, "geometry_hash": self.geometry_hash,
                "camera_registration_supported": self.camera_registration_supported,
                "signal_targets": deepcopy(self._data.get("signal_targets", []))}

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
