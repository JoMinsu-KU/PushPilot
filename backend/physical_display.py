"""Read-only, bounded presentation of already-published physical evidence.

This module deliberately imports no executor, robot port, journal owner, policy,
profile, or inference implementation. The optional collector can fail or stop
without dispatching a command or changing physical-service state. Its vehicle is
an approximate route illustration, never a measured vehicle pose.
"""
from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import threading
import time
from uuid import uuid4


SCHEMA = "pushpilot.physical-display.v1"
MAX_CONFIG_BYTES = 1_000_000
MAX_PACKET_BYTES = 16_000_000
MAX_TAIL_BYTES = 2_000_000
MAX_READ_BYTES = 262_144
MAX_LINE_BYTES = 131_072
MAX_RETAINED_STAGES = 2048
FALLBACK_EPOCH = uuid4().hex


def _encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _iso(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat()


def _read_json(path, limit):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise ValueError("DISPLAY_SOURCE_UNAVAILABLE")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("DISPLAY_SOURCE_OVERSIZE")
    result = json.loads(raw)
    if not isinstance(result, dict):
        raise ValueError("DISPLAY_SOURCE_INVALID")
    return result, raw


def unavailable(reason="DISPLAY_UNAVAILABLE", *, now=None, producer_epoch=FALLBACK_EPOCH):
    return {"schema_version": SCHEMA, "available": False, "reason": reason,
        "producer_epoch": producer_epoch, "sequence": 0, "captured_at": _iso(time.time() if now is None else now),
        "mission_id": None, "plan_id": None, "plan_revision": None,
        "workspace_session_id": None, "map_hash": None, "state": "UNAVAILABLE",
        "phase": "unavailable", "primitive_id": None, "stage_id": None,
        "stage_index": None, "stage_count": None, "stage_status": "none",
        "animation_authority": "confirmed_only", "motion_authority": False,
        "vehicle": {"estimated": True, "moving": False, "route_fraction": None,
            "route_leg_index": None, "leg_fraction": None, "heading": None,
            "confirmed_contact_stages": 0, "total_contact_stages": 0,
            "last_confirmed_at": None},
        "signal": {"phase": "none", "green_count": 0, "green_required": 2}}


def _direction(degrees):
    if type(degrees) not in (int, float) or not math.isfinite(degrees):
        return None
    return ("EAST", "SOUTH", "WEST", "NORTH")[round(degrees / 90) % 4]


def _route_legs(binding, nodes):
    legs = []
    route = binding["route_nodes"]
    for first, second in zip(route, route[1:]):
        a, b = nodes[first], nodes[second]
        dx, dy = b["x_mm"] - a["x_mm"], b["y_mm"] - a["y_mm"]
        if abs(dx) > .01 and abs(dy) > .01 or not (dx or dy):
            raise ValueError("DISPLAY_ROUTE_UNSUPPORTED")
        heading = ("EAST" if dx > 0 else "WEST") if dx else ("SOUTH" if dy > 0 else "NORTH")
        length = math.hypot(dx, dy)
        if legs and legs[-1]["heading"] == heading:
            legs[-1]["length"] += length
        else:
            legs.append({"heading": heading, "length": length})
    return legs


class BoundedJournalTail:
    """Incremental binary reader; incomplete writes never become evidence."""
    def __init__(self):
        self.identity = None
        self.offset = 0
        self.pending = b""
        self.previous_index = None
        self.previous_sha = None
        self.bootstrapped = False
        self.invalid = False

    def read(self, path):
        path = Path(path)
        if path.is_symlink():
            raise ValueError("DISPLAY_JOURNAL_UNAVAILABLE")
        stat = path.stat()
        identity = (str(path), stat.st_dev, stat.st_ino)
        reset = self.identity != identity or stat.st_size < self.offset
        if reset:
            self.identity, self.pending = identity, b""
            self.previous_index = self.previous_sha = None
            self.offset = max(0, stat.st_size - MAX_TAIL_BYTES)
            self.bootstrapped = self.offset == 0
            self.invalid = False
        if self.invalid:
            raise ValueError("DISPLAY_JOURNAL_CHANGED")
        with path.open("rb") as stream:
            stream.seek(self.offset)
            data = stream.read(MAX_READ_BYTES)
        self.offset += len(data)
        combined = self.pending + data
        lines = combined.split(b"\n")
        self.pending = lines.pop()
        if len(self.pending) > MAX_LINE_BYTES:
            raise ValueError("DISPLAY_JOURNAL_OVERSIZE")
        if not self.bootstrapped:
            # The initial tail may begin in the middle of one record.
            if lines:
                lines.pop(0)
                self.bootstrapped = True
        result = []
        for raw in lines:
            if not raw:
                continue
            if len(raw) > MAX_LINE_BYTES:
                self.invalid = True
                raise ValueError("DISPLAY_JOURNAL_OVERSIZE")
            try:
                row = json.loads(raw)
                if not isinstance(row, dict):
                    raise ValueError("Invalid row")
                created = row.get("created_at")
                if type(created) not in (int, float) or not math.isfinite(created):
                    raise ValueError("Invalid event time")
            except (ValueError, TypeError):
                self.invalid = True
                raise ValueError("DISPLAY_JOURNAL_CHANGED") from None
            digest = row.pop("sha256", None)
            index = row.get("index")
            if (type(index) is not int or index < 1 or not isinstance(row.get("payload"), dict)
                    or hashlib.sha256(_encoded(row)).hexdigest() != digest
                    or (self.previous_index is not None and (index != self.previous_index + 1
                        or row.get("previous_sha256") != self.previous_sha))):
                self.invalid = True
                raise ValueError("DISPLAY_JOURNAL_CHANGED")
            self.previous_index, self.previous_sha = index, digest
            result.append(row)
        return result, reset


class PhysicalDisplayService:
    """Independent cached GET projection. All file handles are read-only."""
    def __init__(self, config_path, *, physical_snapshot, map_data, map_hash,
                 interval_s=.5, clock=time.time):
        self.config_path = Path(config_path) if config_path else None
        self.physical_snapshot = physical_snapshot
        self.map_data, self.map_hash = deepcopy(map_data), map_hash
        self.interval_s, self.clock = max(.25, interval_s), clock
        self.producer_epoch = uuid4().hex
        self._cache = unavailable("DISPLAY_NOT_STARTED", now=clock(), producer_epoch=self.producer_epoch)
        self._stop = threading.Event()
        self._thread = None
        self._config_stamp = None
        self._routes, self._primitives = {}, {}
        self._tail = BoundedJournalTail()
        self._mission_binding = None
        self._stages = OrderedDict()
        self._commands = {}
        self._last_stage = None
        self._mission_id = None
        self._sequence = 0

    def start(self):
        if self._thread is None and self.config_path is not None:
            self._thread = threading.Thread(target=self._run, name="physical-display-readonly", daemon=True)
            self._thread.start()
        elif self.config_path is None:
            self._cache = unavailable("PHYSICAL_DISPLAY_DISABLED", now=self.clock(), producer_epoch=self.producer_epoch)

    def close(self):
        # No join: display file latency must never delay physical shutdown.
        self._stop.set()

    def snapshot(self):
        # Assignment is atomic; readers never acquire physical control locks.
        return deepcopy(self._cache)

    def _run(self):
        while not self._stop.is_set():
            self.collect()
            self._stop.wait(self.interval_s)

    def _reset_evidence(self):
        self._mission_binding = self._last_stage = None
        self._stages.clear()
        self._commands.clear()

    def _load_config(self):
        stat = self.config_path.stat()
        stamp = (stat.st_mtime_ns, stat.st_size)
        if self._config_stamp == stamp:
            return
        cfg, _ = _read_json(self.config_path, MAX_CONFIG_BYTES)
        if cfg.get("enabled") is not True:
            raise ValueError("PHYSICAL_DISPLAY_DISABLED")
        ref = cfg["packet"]
        packet_path = Path(ref["path"])
        if not packet_path.is_absolute():
            packet_path = self.config_path.parent / packet_path
        packet, raw = _read_json(packet_path, MAX_PACKET_BYTES)
        if hashlib.sha256(raw).hexdigest() != ref["sha256"]:
            raise ValueError("DISPLAY_PACKET_MISMATCH")
        nodes = {node["id"]: node for node in self.map_data["nodes"]}
        routes = {}
        for code, route in packet["routes"].items():
            binding = cfg["workspace_bindings"][code]
            if binding["map_hash"] != self.map_hash:
                raise ValueError("DISPLAY_MAP_MISMATCH")
            legs = _route_legs(binding, nodes)
            cursor, stages = 0, []
            for step in route["steps"]:
                primitive = packet["primitives"][step["primitive_id"]]
                heading = _direction(step.get("expected_heading_deg"))
                if heading != legs[cursor]["heading"]:
                    following = next((i for i in range(cursor + 1, len(legs))
                                      if legs[i]["heading"] == heading), None)
                    if following is not None:
                        cursor = following
                for index, stage in enumerate(primitive["stages"]):
                    if stage["phase"] == "contact":
                        stages.append({"primitive_id": primitive["id"], "stage_index": index,
                            "stage_id": stage["id"], "leg": cursor})
            routes[code] = {"binding": binding, "steps": route["steps"], "legs": legs,
                            "contacts": stages, "destination": route["destination"]}
        self._routes, self._primitives = routes, packet["primitives"]
        self._journal_path = Path(cfg["journal_root"]) / "events.private.jsonl"
        self._config_stamp = stamp
        self._tail = BoundedJournalTail()
        self._reset_evidence()

    def _accept(self, row, physical):
        payload, kind = row["payload"], row["kind"]
        if kind == "physical_mission_prepared" and payload.get("mission_id") == physical["mission_id"]:
            b = payload.get("workspace_binding", {})
            if all(b.get(key) == physical.get(key) for key in
                   ("plan_id", "plan_revision", "workspace_session_id")) and b.get("map_hash") == self.map_hash:
                self._mission_binding = (physical["mission_id"], physical["plan_revision"])
        elif kind == "mission_primitive_intent":
            self._commands[payload["command_id"]] = payload.get("primitive_id")
            if len(self._commands) > MAX_RETAINED_STAGES:
                del self._commands[next(iter(self._commands))]
        elif kind == "mission_stage_intent":
            intent = payload.get("intent", {})
            if (intent.get("plan_id"), intent.get("revision")) != (physical["mission_id"], physical["plan_revision"]):
                return
            primitive_id = self._commands.get(payload.get("command_id"))
            primitive = self._primitives.get(primitive_id, {})
            index = payload.get("stage_index")
            if type(index) is not int or not 0 <= index < len(primitive.get("stages", [])):
                return
            declared = primitive["stages"][index]
            if (declared.get("id"), declared.get("phase")) != (payload.get("stage_id"), payload.get("phase")):
                return
            self._mission_binding = (physical["mission_id"], physical["plan_revision"])
            key = (payload["command_id"], payload["stage_index"])
            self._stages[key] = {"primitive_id": self._commands.get(payload["command_id"]),
                "stage_id": payload.get("stage_id"), "stage_index": payload["stage_index"],
                "phase": payload.get("phase"), "status": "intent", "at": row["created_at"],
                "request_id": intent.get("request_id"), "source_sequence": intent.get("expected_receiver", {}).get("seq"),
                "session_id": intent.get("expected_receiver", {}).get("session_id")}
            self._last_stage = self._stages[key]
            while len(self._stages) > MAX_RETAINED_STAGES:
                self._stages.popitem(last=False)
        elif kind == "mission_stage_endpoint":
            stage = self._stages.get((payload.get("command_id"), payload.get("stage_index")))
            receipt = payload.get("receipt", {})
            native = payload.get("native_after", {})
            if (stage and receipt.get("endpoint_verified") is True
                    and receipt.get("request_id") == stage["request_id"]
                    and type(stage["source_sequence"]) is int
                    and receipt.get("sequence") == stage["source_sequence"] + 1
                    and receipt.get("session_id") == stage["session_id"]
                    and native.get("sequence") == receipt.get("sequence")
                    and native.get("session_id") == receipt.get("session_id")
                    and native.get("held_disarmed_idle") is True):
                stage.update(status="confirmed", at=row["created_at"])

    @staticmethod
    def _signal(physical):
        signal = physical.get("signal") or {}
        sequence = (physical.get("telemetry") or {}).get("sequence", [])
        recontacts = [r for r in sequence if r.get("kind") == "recontact"]
        if physical.get("state") == "RECONTACTING" or any(r.get("status") == "current" for r in recontacts):
            phase = "recontacting"
        elif any(r.get("status") == "complete" for r in recontacts):
            phase = "passed"
        elif signal.get("waiting"):
            phase = "confirming" if signal.get("stable_green_frames", 0) else "waiting"
        elif signal.get("stable_green_frames", 0) >= signal.get("required_green_frames", 2):
            phase = "admitted"
        else:
            phase = "none"
        return {"phase": phase, "green_count": signal.get("stable_green_frames", 0),
                "green_required": signal.get("required_green_frames", 2)}

    def collect(self):
        """One bounded collection pass; failures affect this cache alone."""
        try:
            self._sequence += 1
            if self.config_path is None:
                raise ValueError("PHYSICAL_DISPLAY_DISABLED")
            self._load_config()
            physical = self.physical_snapshot()
            if physical.get("mission_id") != self._mission_id:
                self._reset_evidence()
                self._mission_id = physical.get("mission_id")
            rows, reset = self._tail.read(self._journal_path)
            if reset:
                self._reset_evidence()
            for row in rows:
                self._accept(row, physical)
            result = unavailable(now=self.clock(), producer_epoch=self.producer_epoch)
            result.update(sequence=self._sequence, mission_id=physical.get("mission_id"),
                plan_id=physical.get("plan_id"), plan_revision=physical.get("plan_revision"),
                workspace_session_id=physical.get("workspace_session_id"), map_hash=self.map_hash,
                state=physical.get("state", "UNAVAILABLE"), signal=self._signal(physical))
            if not physical.get("enabled"):
                result["reason"] = "PHYSICAL_DISPLAY_DISABLED"
            elif physical.get("mission_id") is None:
                result.update(available=True, reason=None, phase="idle")
            elif self._mission_binding != (physical["mission_id"], physical.get("plan_revision")):
                result["reason"] = "DISPLAY_MISSION_BINDING_PENDING"
            else:
                self._project(result, physical)
            self._cache = result
        except Exception as error:
            reason = str(error) if isinstance(error, ValueError) and str(error).startswith(("DISPLAY_", "PHYSICAL_")) else "DISPLAY_SOURCE_UNAVAILABLE"
            self._cache = unavailable(reason, now=self.clock(), producer_epoch=self.producer_epoch)
            self._cache["sequence"] = self._sequence

    def _project(self, result, physical):
        routes = [r for r in self._routes.values() if r["destination"] == physical.get("destination")]
        if len(routes) != 1:
            result["reason"] = "DISPLAY_ROUTE_MISMATCH"
            return
        route = routes[0]
        confirmed_units = {r["id"] for r in (physical.get("telemetry") or {}).get("sequence", [])
                           if r.get("status") == "complete" and r.get("kind") == "route"}
        confirmed = {(s["primitive_id"], s["stage_index"]) for s in self._stages.values()
                     if s["status"] == "confirmed" and s["primitive_id"] is not None}
        contacts = route["contacts"]
        done = [s for s in contacts if s["primitive_id"] in confirmed_units
                or (s["primitive_id"], s["stage_index"]) in confirmed]
        # No observed TCP coordinate or elapsed-time dead reckoning is used.
        leg = done[-1]["leg"] if done else 0
        leg_contacts = [s for s in contacts if s["leg"] == leg]
        leg_done = sum(s["leg"] == leg for s in done)
        fraction = leg_done / len(leg_contacts) if leg_contacts else 0.
        total_length = sum(l["length"] for l in route["legs"])
        route_fraction = (sum(l["length"] for l in route["legs"][:leg])
                          + route["legs"][leg]["length"] * fraction) / total_length
        delivered = physical.get("car", {}).get("arrived") is True
        if delivered:
            leg, fraction, route_fraction = len(route["legs"]) - 1, 1., 1.
        stage = self._last_stage
        state = physical.get("state")
        phase = "pending"
        if state == "HOLD" or physical.get("error"):
            phase = "hold"
        elif physical.get("returning_home") or state == "RETURNING_HOME":
            phase = "return"
        elif state == "COMPLETE":
            phase = "complete"
        elif state == "RECONTACTING":
            phase = "recontact"
        elif physical.get("signal", {}).get("waiting"):
            phase = "signal_wait"
        elif physical.get("vision", {}).get("in_flight") or state == "OBSERVING":
            phase = "muse_review"
        elif stage and state in {"MOVING", "ALIGNING", "CORRECTING", "CLEARING_VIEW"}:
            phase = {"empty": "approach"}.get(stage["phase"], stage["phase"])
            if stage["status"] == "intent":
                phase = "pending"  # Publication precedes dispatch and proves no motion.
        recent = stage and stage["status"] == "confirmed" and 0 <= self.clock() - stage["at"] <= 1.
        result.update(available=True, reason=None, phase=phase,
            primitive_id=stage["primitive_id"] if stage else None,
            stage_id=stage["stage_id"] if stage else None,
            stage_index=stage["stage_index"] if stage else None,
            stage_count=len(self._primitives.get(stage["primitive_id"], {}).get("stages", [])) if stage else None,
            stage_status=stage["status"] if stage else "none")
        result["vehicle"].update(route_fraction=route_fraction, route_leg_index=leg,
            leg_fraction=fraction, heading=route["legs"][leg]["heading"],
            confirmed_contact_stages=len(done), total_contact_stages=len(contacts),
            moving=bool(recent and phase == "contact" and not delivered),
            last_confirmed_at=_iso(stage["at"]) if stage and stage["status"] == "confirmed" else None)
