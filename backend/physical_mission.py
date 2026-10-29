"""Durable single-owner physical mission orchestration, separate from simulation.

All robot IO is performed by a configured measured driver. No background task is
resumed after process loss, and an uncertain POST is never retried as a new move.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path
import sqlite3
import time
from uuid import uuid4

from backend.core import CommandError
from backend.robot_control.mission_policy import DecisionKind, MissionPolicy, Phase
from backend.robot_control.service import ProcessLock


class PhysicalMissionService:
    def __init__(self, store, directory, *, driver=None, poll_interval_s=2., clock=time.time):
        self.store, self.driver, self.clock = store, driver, clock
        self.poll_interval_s = poll_interval_s
        self.root = Path(directory)
        self.root.mkdir(parents=True, exist_ok=True)
        self.owner = ProcessLock(self.root / "physical-mission.owner.lock")
        self.owner.acquire()
        self.db = sqlite3.connect(self.root / "physical-mission.sqlite3")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
          CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS requests (id TEXT PRIMARY KEY, payload TEXT NOT NULL, response TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY AUTOINCREMENT, at REAL, kind TEXT, value TEXT);
        """)
        self.task = None
        self.monitor_task = None
        self.closing = asyncio.Event()
        self.lock = asyncio.Lock()
        self.stopping = asyncio.Event()
        self.stop_generation = 0
        row = self.db.execute("SELECT value FROM state WHERE id=1").fetchone()
        self.status = json.loads(row[0]) if row else self._empty()
        self.status["vision"].update(in_flight=False, kind=None, started_at=None)
        if row and self.status["state"] not in {"DISABLED", "READY", "COMPLETE", "HOLD"}:
            self.status.update(state="HOLD", available=False, error="RESTART_REQUIRES_RECONCILIATION",
                               stage_label="Previous mission requires reconciliation")
            self.status["vision"]["in_flight"] = False
        if self.driver is None:
            self._disable_unconfigured()
        self._persist("SERVICE_OPENED", {"automatic_resume": False})

    def _empty(self):
        return {"schema_version": "pushpilot.physical.v1", "enabled": self.driver is not None,
            "available": False, "state": "DISABLED" if self.driver is None else "READY",
            "revision": 0, "mission_id": None, "destination": None, "stage_label": "Physical setup required",
            "progress": {"completed": 0, "total": 0}, "robot": {"connected": False, "stationary": False, "at_start": False},
            "car": {"arrived": False, "aligned": False, "heading_error_deg": None},
            "signal": {"color": "UNKNOWN", "waiting": False, "stable_green_frames": 0, "required_green_frames": 2},
            "vision": {"in_flight": False, "kind": None, "started_at": None, "last_result_at": None, "summary": None},
            "returning_home": False, "error": None,
            "blockers": ["A qualified measured physical mission release is not installed."], "capabilities": {},
            "plan_id": None, "plan_revision": None, "workspace_session_id": None}

    def _disable_unconfigured(self):
        """Retain mission history without advertising a removed runtime release."""
        self.status.update(enabled=False, available=False, capabilities={}, returning_home=False,
            blockers=["A qualified measured physical mission release is not installed."])
        self.status["robot"] = {"connected": False, "stationary": False, "at_start": False}
        self.status["signal"].update(waiting=False, stable_green_frames=0)
        if self.status["state"] in {"DISABLED", "READY"}:
            self.status.update(state="DISABLED", stage_label="Physical setup required")

    def _persist(self, kind, evidence=None):
        with self.db:
            self.status["revision"] += 1
            self.db.execute("INSERT OR REPLACE INTO state VALUES(1,?)", (json.dumps(self.status, allow_nan=False),))
            self.db.execute("INSERT INTO events(at,kind,value) VALUES(?,?,?)",
                            (self.clock(), kind, json.dumps(evidence or {}, allow_nan=False)))

    def snapshot(self):
        return deepcopy(self.status)

    def start_monitor(self):
        if self.driver is not None and self.monitor_task is None:
            self.monitor_task = asyncio.create_task(self._monitor(), name="physical-readiness")

    async def _monitor(self):
        while not self.closing.is_set():
            try:
                await asyncio.wait_for(self.closing.wait(), timeout=5.)
                break
            except TimeoutError:
                pass
            if not self.lock.locked() and not (self.task and not self.task.done()):
                async with self.lock:
                    before = self.snapshot()
                    await self.refresh_readiness()
                    if self.status != before:
                        self._persist("READINESS_CHANGED")

    async def refresh_readiness(self):
        if self.driver is None:
            self._disable_unconfigured()
            return self.snapshot()
        if self.task and not self.task.done():
            return self.snapshot()
        if self.status["state"] == "HOLD":
            # Reconciliation is an explicit commissioning operation, never a UI poll.
            return self.snapshot()
        try:
            ready = await asyncio.to_thread(self.driver.readiness)
            capabilities = dict(ready.get("capabilities", {}))
            destinations = ready.get("destinations", capabilities.get("destinations", []))
            capabilities["destinations"] = sorted({value for value in destinations if isinstance(value, str)})
            self.status.update(enabled=True, available=ready.get("available", ready.get("ready")) is True,
                               blockers=list(ready.get("blockers", ready.get("reasons", []))), capabilities=capabilities)
            self.status["robot"] = {"connected": ready.get("connected") is True,
                                    "stationary": ready.get("stationary") is True,
                                    "at_start": ready.get("at_start") is True}
        except Exception:
            self.status.update(available=False, blockers=["Physical driver readiness is unavailable."])
            self.status["robot"]["connected"] = False
        return self.snapshot()

    def _bound_workspace(self, command):
        state = self.store.snapshot()
        plan, goal = state.get("plan") or {}, state.get("goal") or {}
        route = plan.get("route") or {}
        m = self.store.map_definition
        expected = {"workspace_session_id": state["session_id"], "plan_id": plan.get("id"),
            "plan_revision": plan.get("revision"), "destination": goal.get("destination"),
            "route_nodes": route.get("node_ids") if isinstance(route, dict) else None,
            "map_id": m.id, "map_version": m.version, "map_hash": m.geometry_hash}
        if not isinstance(route, dict) or any(route.get(key) != expected[key] for key in
                ("destination", "map_id", "map_version", "map_hash")):
            raise CommandError("The stored route does not match the current physical map and destination.", 409)
        if (state["state"] != "PLAN_READY" or goal.get("provider") != "meta" or not plan.get("planning")
                or any(command.get(key) != value for key, value in expected.items())):
            raise CommandError("Physical execution requires the exact current live MUSE plan and map.", 409)
        return expected

    def _existing(self, command):
        row = self.db.execute("SELECT payload,response FROM requests WHERE id=?", (command["request_id"],)).fetchone()
        if row:
            if json.loads(row[0]) != command:
                raise CommandError("This physical request ID already belongs to another payload.", 409)
            return json.loads(row[1])
        return None

    def _save_request(self, command):
        response = self.snapshot()
        with self.db:
            self.db.execute("INSERT INTO requests VALUES(?,?,?)",
                            (command["request_id"], json.dumps(command), json.dumps(response)))
        return response

    async def start(self, command):
        async with self.lock:
            prior = self._existing(command)
            if prior is not None:
                return prior
            if command["expected_revision"] != self.status["revision"]:
                raise CommandError("Physical status changed; refresh before starting.", 409)
            if self.task and not self.task.done() or self.status["state"] == "HOLD":
                raise CommandError("A physical mission is active or requires reconciliation.", 409)
            binding = self._bound_workspace(command)
            stop_generation = self.stop_generation
            await self.refresh_readiness()
            if not self.status["available"] or self.driver is None:
                raise CommandError("The physical route is not released: " + "; ".join(self.status["blockers"]), 409)
            if binding["destination"] not in self.status["capabilities"].get("destinations", []):
                raise CommandError("The selected destination has no released physical route at the current source.", 409)
            plan = await asyncio.to_thread(self.driver.prepare, binding)
            # Preparation may take seconds. Revalidate before committing a mission.
            self._bound_workspace(command)
            context = await asyncio.to_thread(self.driver.context)
            if self.stop_generation != stop_generation:
                await asyncio.to_thread(self.driver.hold, "STOP_DURING_PREPARATION")
                raise CommandError("Mission preparation was cancelled by a stop request.", 409)
            policy = MissionPolicy(plan)
            state = policy.initial_state(context.session_id)
            self.stopping.clear()
            self.status.update(state="STARTING", available=False, mission_id=plan.id,
                destination=command["destination"], stage_label="Checking fixed start", error=None, blockers=[],
                plan_id=command["plan_id"], plan_revision=command["plan_revision"],
                workspace_session_id=command["workspace_session_id"], returning_home=False)
            self.status["car"] = {"arrived": False, "aligned": False, "heading_error_deg": None}
            self.status["signal"] = {"color": "UNKNOWN", "waiting": False, "stable_green_frames": 0, "required_green_frames": 2}
            self.status["progress"] = {"completed": 0, "total": len(plan.steps)}
            self._persist("MISSION_ACCEPTED", {"workspace": binding, "policy": asdict(plan), "state": asdict(state)})
            response = self._save_request(command)
            self.task = asyncio.create_task(self._run(policy, state, command), name="physical-mission")
            return response

    async def stop(self, command):
        # Signal cancellation before waiting for a potentially slow prepare().
        self.stop_generation += 1
        self.stopping.set()
        async with self.lock:
            prior = self._existing(command)
            if prior is not None:
                return prior
            # A stop remains available while status revisions advance during a move.
            self.stopping.set()
            self.status.update(state="HOLD", available=False, error="OPERATOR_STOP", stage_label="Stop requested")
            self._persist("STOP_REQUESTED", {"request_id": command["request_id"]})
            if self.driver is not None:
                try:
                    await asyncio.to_thread(self.driver.hold, "OPERATOR_STOP")
                except Exception:
                    self.status.update(error="STOP_DELIVERY_UNCONFIRMED", stage_label="Stop delivery unconfirmed")
                    self._persist("STOP_DELIVERY_UNCONFIRMED")
            return self._save_request(command)

    async def _observe(self, state):
        signal = state.phase in {Phase.WAIT_SIGNAL, Phase.ENTRY_SIGNAL}
        self.status["vision"].update(in_flight=True, kind="signal" if signal else "car", started_at=self.clock())
        self.status["stage_label"] = "Checking signal · MUSE" if signal else "Reviewing car · MUSE"
        self._persist("OBSERVATION_STARTED", {"phase": state.phase})
        try:
            result = await asyncio.to_thread(self.driver.observe, state)
            self.status["vision"].update(last_result_at=self.clock(), summary=result.get("summary"))
            if result.get("signal"):
                self.status["signal"]["color"] = result["signal"].color
            return result
        finally:
            self.status["vision"]["in_flight"] = False
            self._persist("OBSERVATION_FINISHED")

    async def _run(self, policy, state, command):
        observation = {}
        observation_queue = []
        failure_count = 0
        try:
            while not self.stopping.is_set():
                self._bound_workspace(command)
                context = await asyncio.to_thread(self.driver.context)
                decision = policy.decide(state, context, car=observation.get("car"), signal=observation.get("signal"),
                                         start=observation.get("start"), command_id=uuid4().hex)
                state = decision.state
                self.status["robot"].update(connected=True, stationary=context.stationary,
                                            at_start=context.context_id == policy.plan.start_context_id)
                self.status["signal"].update(waiting=state.phase in {Phase.WAIT_SIGNAL, Phase.ENTRY_SIGNAL},
                    stable_green_frames=min(2, len(state.green_image_sha256s)))
                self.status["car"].update(arrived=state.vehicle_delivered, aligned=state.vehicle_delivered)
                self.status["progress"]["completed"] = min(len(policy.plan.steps), state.step_index + int(state.vehicle_delivered))
                self.status["returning_home"] = state.phase == Phase.RETURNING or state.pending_role == "RETURN"
                self.status["stage_label"] = decision.reason.replace("_", " ").capitalize()
                # Persist every intent BEFORE the only motion call. A crash cannot recreate it.
                self._persist("POLICY_DECISION", {"decision": asdict(decision)})
                if self.stopping.is_set():
                    break
                if decision.kind == DecisionKind.DISPATCH:
                    self._bound_workspace(command)
                    self.status["state"] = {"RECONTACT": "RECONTACTING", "RETURN": "RETURNING_HOME",
                        "PARKING": "ALIGNING", "CORRECTION": "CORRECTING", "CLEARANCE": "CLEARING_VIEW"}.get(state.pending_role, "MOVING")
                    self.status["robot"].update(stationary=False, at_start=False)
                    self._persist("PRIMITIVE_DISPATCH_INTENT", {"primitive": decision.primitive_id, "command_id": decision.command_id})
                    receipt = await asyncio.to_thread(self.driver.execute, decision.primitive_id, decision.command_id)
                    state = policy.accept_receipt(state, receipt)
                    self._persist("PRIMITIVE_RECEIPT", {"receipt": asdict(receipt), "state": asdict(state)})
                    observation = {}
                    observation_queue = []
                elif decision.kind in {DecisionKind.OBSERVE, DecisionKind.WAIT}:
                    self.status["state"] = "WAITING_SIGNAL" if state.phase in {Phase.WAIT_SIGNAL, Phase.ENTRY_SIGNAL} else "OBSERVING"
                    if observation_queue:
                        observation = observation_queue.pop(0)
                        continue
                    try:
                        observation = await self._observe(state)
                        samples = observation.pop("samples", [])
                        if samples:
                            observation, observation_queue = samples[0], list(samples[1:])
                        failure_count = 0
                    except Exception as error:
                        # Re-observe only; no replay and no runtime restart. Repeated failures terminate.
                        observation = {}
                        failure_count += 1
                        self._persist("OBSERVATION_UNAVAILABLE", {"consecutive_failures": failure_count,
                            "exception_type": type(error).__name__, "code": getattr(error, "code", None)})
                        if failure_count >= 3:
                            raise RuntimeError("OBSERVATION_SERVICE_UNAVAILABLE") from None
                    if not self.stopping.is_set() and not observation_queue:
                        try:
                            await asyncio.wait_for(self.stopping.wait(), timeout=self.poll_interval_s)
                        except TimeoutError:
                            pass
                elif decision.kind == DecisionKind.COMPLETE:
                    self.status.update(state="COMPLETE", returning_home=False, stage_label="Delivered · Robot returned to start")
                    self.status["robot"].update(stationary=True, at_start=True)
                    self.status["progress"]["completed"] = len(policy.plan.steps)
                    self._persist("MISSION_COMPLETE", {"state": asdict(state)})
                    return
                else:
                    self.status.update(state="HOLD", error=decision.reason, available=False)
                    await asyncio.to_thread(self.driver.hold, decision.reason)
                    self._persist("MISSION_HELD", {"state": asdict(state)})
                    return
        except Exception as error:
            code = getattr(error, "code", None) or (str(error) if str(error) == "OBSERVATION_SERVICE_UNAVAILABLE" else "PHYSICAL_MISSION_INTERRUPTED")
            self.status.update(state="HOLD", error=code, available=False, stage_label="Mission stopped · Review required")
            self._persist("MISSION_INTERRUPTED", {"exception_type": type(error).__name__, "state": asdict(state)})
            try:
                await asyncio.to_thread(self.driver.hold, code)
            except Exception:
                self.status["error"] = "CONTROL_HOLD_UNCONFIRMED"
                self._persist("CONTROL_HOLD_UNCONFIRMED")
        finally:
            self.status["vision"]["in_flight"] = False
            self._persist("WORKER_EXITED", {"automatic_resume": False})

    async def close(self):
        self.closing.set()
        if self.monitor_task:
            await self.monitor_task
        self.stopping.set()
        if self.task and not self.task.done():
            try:
                await asyncio.to_thread(self.driver.hold, "APPLICATION_SHUTDOWN")
            except Exception:
                pass
            # Never cancel an in-flight thread and pretend the hardware stopped.
            await self.task
        if self.driver is not None:
            await asyncio.to_thread(self.driver.close)
        self.db.close()
        self.owner.close()
