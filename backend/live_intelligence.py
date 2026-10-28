"""Explicit native-frame MUSE operations, bound to the simulation supervisor.

The preview remains ephemeral. Only deliberate operations copy original bytes
to the private SQLite evidence ledger. No operation emits a robot command.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
import hashlib
import json
import time
from uuid import uuid4, uuid5, UUID

from backend.core import CommandError
from backend.meta import ProviderError
from backend.scene import SceneError, MODEL
from backend.planning_provider import MetaPlanningProvider, validate_result as validate_plan
from backend.planning_provider import PROMPT_VERSION, SCHEMA_VERSION
from backend.action_review import validate_result as validate_action
from backend.live_review_provider import (MetaLiveReviewProvider, validate_signal_result,
    ACTION_PROMPT_VERSION, ACTION_SCHEMA_VERSION, SIGNAL_PROMPT_VERSION, SIGNAL_SCHEMA_VERSION)


class LiveIntelligenceService:
    """Reserve once, release locks for inference, and revalidate before commit."""

    def __init__(self, store, camera, *, api_key="", planning_provider=None, review_provider=None,
                 voice=None, timeout_seconds=50.0, signal_result_max_age_seconds=30.0):
        self.store, self.camera, self.voice = store, camera, voice
        self.planner = planning_provider or MetaPlanningProvider(api_key)
        self.reviewer = review_provider or MetaLiveReviewProvider(api_key)
        self.timeout = timeout_seconds
        # A simulation policy only, not a qualified physical stopping tolerance.
        self.signal_max_age = signal_result_max_age_seconds
        self.boot = uuid4().hex
        with store._lock, store._db:
            store._db.executescript("""
                CREATE TABLE IF NOT EXISTS live_evidence_frames
                  (id TEXT PRIMARY KEY, metadata TEXT NOT NULL, data BLOB NOT NULL);
                CREATE TABLE IF NOT EXISTS live_operations
                  (id TEXT PRIMARY KEY, kind TEXT NOT NULL, status TEXT NOT NULL,
                   binding TEXT NOT NULL, result TEXT);
                CREATE TABLE IF NOT EXISTS live_action_contexts
                  (review_id TEXT PRIMARY KEY, binding TEXT NOT NULL);
            """)
            for row in store._db.execute("SELECT id FROM live_operations WHERE status='pending'").fetchall():
                response = json.dumps({"detail": "The live operation was interrupted. Create a new request; no result was replayed."})
                store._db.execute("UPDATE requests SET status=409,response=? WHERE id=? AND status=102", (response, row["id"]))
            store._db.execute("UPDATE live_operations SET status='interrupted' WHERE status='pending'")
            state = store._load()
            if state.pop("planning_pending", None):
                state["revision"] += 1
                store._event(state, "LIVE_PLANNING_INTERRUPTED", "Planning interrupted", "Create a new plan. No pending inference was replayed.", "system")
                store._save(state)

    def _map(self):
        m = self.store.map_definition
        return {"map_id": m.id, "map_version": m.version, "map_hash": m.geometry_hash}

    def _planning_context(self, frame):
        """Ground every symbolic node in the unchanged source image."""
        import cv2
        import numpy as np
        context = self.store.map_definition.planning_context()
        nodes = self.store.map_definition.data["nodes"]
        points = np.array([[node["x_mm"], node["y_mm"]] for node in nodes], dtype=np.float64)
        matrix = np.array(frame["metadata"]["registration"]["homography"], dtype=np.float64)
        projected = cv2.perspectiveTransform(points.reshape(-1,1,2), matrix).reshape(-1,2)
        if not np.isfinite(projected).all():
            raise CommandError("The registered node projection is invalid.")
        context["node_image_positions"] = [{"node_id": node["id"], "pixel_xy": point.tolist()} for node,point in zip(nodes,projected)]
        context["image_grounding"] = {"frame_id": frame["metadata"]["id"], "width": frame["metadata"]["width"],
                                      "height": frame["metadata"]["height"], "source": "fixed_drawing_projection",
                                      "measured_car_pose": False}
        return context

    @staticmethod
    def _digest(kind, payload):
        return hashlib.sha256(json.dumps({"action": kind, "payload": payload}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def _prior(self, kind, payload):
        row = self.store._db.execute("SELECT * FROM requests WHERE id=?", (payload["request_id"],)).fetchone()
        if row is None:
            return None
        if row["digest"] != self._digest(kind, payload):
            raise CommandError("This request ID is already bound to a different command.")
        if row["status"] == 102:
            raise CommandError("This live request is already pending. No duplicate inference was sent.")
        return json.loads(row["response"]), row["status"]

    def _check_revision(self, state, payload):
        if state["revision"] != payload["expected_revision"]:
            raise CommandError("Workspace changed. Refresh state before submitting this command.")

    def require_current_live_view(self, state):
        planning = (state.get("plan") or {}).get("planning")
        if planning:
            self.camera.check_binding(planning["frame"])

    def _reserve(self, kind, payload, binding):
        self.store._db.execute("INSERT INTO requests(id,digest,status,response) VALUES(?,?,102,?)",
                               (payload["request_id"], self._digest(kind, payload), json.dumps({"detail": "MUSE operation pending."})))
        self.store._db.execute("INSERT INTO live_operations(id,kind,status,binding) VALUES(?,?,'pending',?)",
                               (payload["request_id"], kind, json.dumps(binding)))

    def _finish(self, request_id, response, status, evidence=None):
        self.store._db.execute("UPDATE requests SET status=?,response=? WHERE id=? AND status=102",
                               (status, json.dumps(response), request_id))
        self.store._db.execute("UPDATE live_operations SET status=?,result=? WHERE id=? AND status='pending'",
                               ("accepted" if status == 200 else "rejected", json.dumps(evidence), request_id))
        return response, status

    def _inputs_selected(self, request_id, **inputs):
        row = self.store._db.execute("SELECT binding FROM live_operations WHERE id=?", (request_id,)).fetchone()
        binding = json.loads(row["binding"])
        binding.update(inputs)
        self.store._db.execute("UPDATE live_operations SET binding=? WHERE id=?", (json.dumps(binding), request_id))

    def _fail(self, request_id, message, status=502, evidence=None, *, detail=None):
        with self.store._lock, self.store._db:
            state = self.store._load()
            if (state.get("planning_pending") or {}).get("request_id") == request_id:
                state.pop("planning_pending", None)
                state["revision"] += 1
                self.store._event(state, "LIVE_PLANNING_FAILED", "No live plan accepted", message, "meta", record=evidence)
                self.store._save(state)
            return self._finish(request_id, {"detail": message if detail is None else detail}, status, evidence)

    def _save_frame(self, frame):
        metadata = deepcopy(frame["metadata"])
        observation_id = uuid4().hex
        metadata.update(native_frame_id=metadata["id"], id=observation_id,
                        image_url=f"/api/v1/live-evidence/frames/{observation_id}/image")
        self.store._db.execute("INSERT INTO live_evidence_frames(id,metadata,data) VALUES(?,?,?)",
                               (observation_id, json.dumps(metadata), frame["data"]))
        return {"metadata": metadata, "data": frame["data"]}

    def frame(self, frame_id):
        with self.store._lock:
            row = self.store._db.execute("SELECT data FROM live_evidence_frames WHERE id=?", (frame_id,)).fetchone()
            if row is None:
                raise SceneError(404, "Live evidence frame not found.", "LIVE_EVIDENCE_NOT_FOUND")
            return bytes(row["data"])

    def operations(self):
        with self.store._lock:
            return {"schema_version": "pushpilot.live-operations.v1", "motion_authority": False,
                    "operations": [dict(row, binding=json.loads(row["binding"]), result=json.loads(row["result"]) if row["result"] else None)
                                   for row in self.store._db.execute("SELECT id,kind,status,binding,result FROM live_operations ORDER BY rowid DESC LIMIT 100")]}

    async def _new_frame(self, *, after_sequence=None, not_before=None):
        deadline = time.monotonic() + 2.5
        while True:
            try:
                return self.camera.capture(after_sequence=after_sequence, not_before=not_before)
            except SceneError as error:
                if error.code != "LIVE_CAPTURE_NOT_NEW" or time.monotonic() >= deadline:
                    raise
                await asyncio.sleep(0.05)

    def _voice_receipt(self, state, payload):
        if payload.get("source", "typed") != "voice":
            return None
        if not self.voice or not payload.get("transcript_id"):
            raise CommandError("A current voice transcript receipt is required. Review and confirm its text first.", 422)
        try:
            receipt = self.voice.get_transcript(payload["transcript_id"])
        except Exception:
            raise CommandError("The voice transcript expired or changed. Transcribe and confirm it again.") from None
        expected = {"session_id": state["session_id"], "workspace_revision": state["revision"],
                    "map": {"id": self.store.map_definition.id, "version": self.store.map_definition.version,
                            "geometry_hash": self.store.map_definition.geometry_hash}}
        if receipt.get("binding") != expected:
            raise CommandError("The voice transcript belongs to a different workspace or map revision.")
        return {"transcript_id": payload["transcript_id"], "original_text": receipt["text"],
                "confirmed_text": payload["text"], "audio_source": receipt["audio_source"]}

    async def plan(self, payload):
        kind = "live-plans"
        if not isinstance(payload.get("text"), str) or not payload["text"].strip() or len(payload["text"]) > 2000:
            raise CommandError("Enter a nonempty goal of at most 2000 characters.", 422)
        with self.store._lock, self.store._db:
            prior = self._prior(kind, payload)
            if prior:
                return prior
            state = self.store._load()
            self._check_revision(state, payload)
            if state["state"] not in {"IDLE", "PLAN_READY"}:
                raise CommandError("Live planning is allowed only during non-executing preparation.")
            voice = self._voice_receipt(state, payload)
            # Invalidate an old approvable plan before any camera/provider work.
            state.update(state="IDLE", goal=None, plan=None, approved=False, stopped=False, review=None, current_step=0)
            state["signal"] = self.store._empty_signal()
            state["revision"] += 1
            state["planning_pending"] = {"request_id": payload["request_id"], "source": "meta"}
            binding = {"session_id": state["session_id"], "workspace_revision": state["revision"],
                       **self._map(), "text": payload["text"], "voice": voice}
            self._reserve(kind, payload, binding)
            self.store._event(state, "LIVE_PLANNING_REQUESTED", "Live MUSE planning requested", "A native frame and the selected map graph will be sent. Prior approval was cleared.", "operator")
            self.store._save(state)
        started = time.monotonic()
        evidence = None
        try:
            frame = self.camera.capture()
            with self.store._lock, self.store._db:
                frame = self._save_frame(frame)
                self._inputs_selected(payload["request_id"], frame=frame["metadata"], prompt_version=PROMPT_VERSION, schema_version=SCHEMA_VERSION)
            context = {"map": self._planning_context(frame), "frame": frame["metadata"],
                       "operator_constraints": payload.get("route_constraints")}
            with self.store._lock, self.store._db:
                self._inputs_selected(payload["request_id"], map_context=context["map"],
                                      operator_constraints=payload.get("route_constraints"))
            result = await asyncio.wait_for(asyncio.to_thread(self.planner.plan, payload["text"], context, frame["data"]), self.timeout)
            result = validate_plan(result, context)
            provider_result = deepcopy(result)
            if result["scene_assessment"]["status"] != "clear":
                result.update(requires_clarification=True, route_nodes=[])
                result["summary"] = ("The live scene needs clarification: " + result["scene_assessment"]["detail"])[:500]
            route = None
            if not result["requires_clarification"]:
                m = self.store.map_definition
                route = m.route_from_nodes(result["destination"], result["route_nodes"])
                m.validate_route_constraints(route, result["constraints"])
                if payload.get("route_constraints") is not None:
                    m.validate_route_constraints(route, payload["route_constraints"])
            evidence = {"id": uuid4().hex, "request_id": payload["request_id"], "source": "meta",
                        "input_kind": "live_native_frame_and_graph", "model": MODEL,
                        "prompt_version": PROMPT_VERSION, "schema_version": SCHEMA_VERSION,
                        "simulation_only": True, "motion_authority": False,
                        **binding, "frame": frame["metadata"], "result": result,
                        "provider_result": provider_result,
                        "map_context": context["map"],
                        "elapsed_ms": round((time.monotonic() - started) * 1000)}
            with self.store._lock, self.store._db:
                state = self.store._load()
                if (state["revision"] != binding["workspace_revision"] or state["session_id"] != binding["session_id"]
                        or (state.get("planning_pending") or {}).get("request_id") != payload["request_id"]
                        or self._map() != {key: binding[key] for key in self._map()}):
                    raise CommandError("The planning request was superseded or cancelled.")
                self.camera.check_binding(frame["metadata"])
                state.pop("planning_pending", None)
                state["revision"] += 1
                if route is not None:
                    state["goal"] = {"text": payload["text"], "destination": result["destination"], "summary": result["summary"],
                                     "source": payload.get("source", "typed"), "provider": "meta"}
                    if voice:
                        state["goal"]["voice_receipt"] = voice
                    state["plan"] = {"id": str(uuid4()), "revision": state["revision"], "route": route,
                                     "steps": self.store._route_steps(route), "planning": evidence}
                    state["state"] = "PLAN_READY"
                self.store._event(state, "LIVE_PLAN_READY" if route else "LIVE_PLAN_CLARIFICATION",
                                  "MUSE route prepared" if route else "Planning needs clarification", result["summary"], "meta", record=evidence)
                self.store._save(state)
                return self._finish(payload["request_id"], self.store._snapshot(state), 200, evidence)
        except SceneError as error:
            # SceneError contains bounded, credential-free camera diagnostics.
            # Preserve them for both the failed request receipt and its event;
            # registration failures are not workspace revision conflicts.
            return self._fail(payload["request_id"], f"{error.code}: {error}", error.status_code, evidence,
                              detail={"code": error.code, "message": str(error)})
        except CommandError:
            return self._fail(payload["request_id"], "Live camera, registration or workspace changed. No plan was accepted. Refresh and try again.", 409, evidence)
        except (ValueError, ProviderError):
            return self._fail(payload["request_id"], "MUSE returned an invalid route or failed to plan. No alternative route or demo result was substituted.", 502, evidence)
        except asyncio.CancelledError:
            self._fail(payload["request_id"], "Live planning was interrupted. No plan was accepted.", 503, evidence)
            raise
        except Exception:
            return self._fail(payload["request_id"], "Live MUSE planning failed. No plan was accepted.", 502, evidence)

    def _action_binding(self, state):
        self.store._require_current_map(state)
        self.require_current_live_view(state)
        if not state["approved"] or state["state"] != "REVIEW_REQUIRED" or state["review"]["verdict"] != "PENDING":
            raise CommandError("An approved simulated action must be awaiting its bound review.")
        step = state["plan"]["steps"][state["current_step"]]
        action = deepcopy(step)
        route = state["plan"]["route"]
        action["drawing_geometry"] = {"route_points_mm": route["points_mm"],
            "junction": next((item for item in (route.get("visualization") or {}).get("junctions", []) if item["node_id"] == step.get("node_id")), None),
            "segment": next((item for item in (route.get("visualization") or {}).get("segments", []) if item["id"] == step.get("route_segment_id")), None)}
        return {"session_id": state["session_id"], "plan_id": state["plan"]["id"], "plan_revision": state["plan"]["revision"],
                "review_id": state["review"]["id"], "action_id": step["id"], "server_action": action,
                "action_receipt": deepcopy(state.get("action_receipt")), **self._map()}

    def _bind_action(self, state, before):
        binding = {**self._action_binding(state), "before": before["metadata"], "boot": self.boot}
        self.store._db.execute("INSERT INTO live_action_contexts(review_id,binding) VALUES(?,?)", (binding["review_id"], json.dumps(binding)))

    @staticmethod
    def _image_geometry(geometry, frame):
        import cv2
        import numpy as np
        matrix = np.array(frame["metadata"]["registration"]["homography"], dtype=np.float64)
        def project(points):
            result = cv2.perspectiveTransform(np.array(points, dtype=np.float64).reshape(-1,1,2), matrix).reshape(-1,2)
            if not np.isfinite(result).all():
                raise CommandError("Drawing projection is invalid for this frame.")
            return result.tolist()
        result = {"pixel_frame_id": frame["metadata"]["id"], "route_points_px": project(geometry["route_points_mm"]),
                  "source": "drawing_projection", "measured_car_pose": False}
        if geometry["segment"]:
            result["current_segment_px"] = project(geometry["segment"]["points_mm"])
        if geometry["junction"]:
            result["stop_line_px"] = project(geometry["junction"]["stop_line_mm"])
        return result

    def advance(self, payload):
        """Pin BEFORE and complete one abstract action, never a physical action."""
        kind = "live-advance"
        with self.store._lock, self.store._db:
            prior = self._prior(kind, payload)
            if prior:
                return prior
            state = self.store._load()
            self._check_revision(state, payload)
            if state["state"] != "READY" or not state["approved"] or self.store._kind(state) == "CROSS":
                raise CommandError("A non-crossing simulated action must be ready and approved.")
            self.store._require_current_map(state)
            self.require_current_live_view(state)
            before = self._save_frame(self.camera.capture())
            self.store._run_step(state)
            self._bind_action(state, before)
            state["revision"] += 1
            self.store._save(state)
            self._reserve(kind, payload, {"review_id": state["review"]["id"], "before": before["metadata"]})
            return self._finish(payload["request_id"], self.store._snapshot(state), 200)

    async def run(self, payload):
        """One deliberate action/reobservation followed by automatic live review."""
        kind = "live-run"
        with self.store._lock, self.store._db:
            prior = self._prior(kind, payload)
            if prior:
                return prior
            state = self.store._load()
            self._check_revision(state, payload)
            if state["state"] not in {"READY", "REOBSERVE"}:
                raise CommandError("A simulated action or reobservation must be ready.")
            mode = "reobserve" if state["state"] == "REOBSERVE" else "advance"
            self._reserve(kind, payload, {"session_id": state["session_id"], "stage": mode})
        try:
            child = {"request_id": str(uuid5(UUID(payload["request_id"]), mode)), "expected_revision": payload["expected_revision"]}
            response, status = self.reobserve(child) if mode == "reobserve" else self.advance(child)
            if status == 200:
                review = {"request_id": str(uuid5(UUID(payload["request_id"]), "review")), "expected_revision": response["revision"],
                          "review_id": response["review"]["id"], "expected_visual": response["review"]["expected"]}
                response, status = await self.review_action(review)
            with self.store._lock, self.store._db:
                return self._finish(payload["request_id"], response, status)
        except (CommandError, SceneError):
            return self._fail(payload["request_id"], "The live action or observation context changed. No additional action was run.", 409)
        except asyncio.CancelledError:
            self._fail(payload["request_id"], "The live action review was interrupted. Inspect the pending action before continuing.", 503)
            raise
        except Exception:
            return self._fail(payload["request_id"], "The live action operation failed. Inspect the action evidence before continuing.", 502)

    async def review_action(self, payload):
        kind = "live-action-reviews"
        with self.store._lock, self.store._db:
            prior = self._prior(kind, payload)
            if prior:
                return prior
            state = self.store._load()
            self._check_revision(state, payload)
            binding = self._action_binding(state)
            if payload["review_id"] != binding["review_id"]:
                raise CommandError("The live review belongs to a different action.")
            row = self.store._db.execute("SELECT binding FROM live_action_contexts WHERE review_id=?", (binding["review_id"],)).fetchone()
            if not row:
                raise CommandError("No server-captured BEFORE frame is bound to this action. Use live advance for the next action.")
            captured = json.loads(row["binding"])
            if captured["boot"] != self.boot or any(captured[key] != binding[key] for key in binding):
                raise CommandError("The action capture belongs to an earlier execution context.")
            for pending in self.store._db.execute("SELECT binding FROM live_operations WHERE status='pending' AND kind=?", (kind,)):
                if json.loads(pending["binding"])["review_id"] == binding["review_id"]:
                    raise CommandError("A live comparison is already pending for this action.")
            before_row = self.store._db.execute("SELECT data FROM live_evidence_frames WHERE id=?", (captured["before"]["id"],)).fetchone()
            before = {"metadata": captured["before"], "data": bytes(before_row["data"])}
            binding["workspace_revision"] = state["revision"]
            self._reserve(kind, payload, binding)
        evidence = None
        started = time.monotonic()
        try:
            self.camera.check_binding(before["metadata"])
            after = await self._new_frame(after_sequence=before["metadata"]["sequence"], not_before=started)
            with self.store._lock, self.store._db:
                after = self._save_frame(after)
                self._inputs_selected(payload["request_id"], before=before["metadata"], after=after["metadata"],
                                      prompt_version=ACTION_PROMPT_VERSION, schema_version=ACTION_SCHEMA_VERSION)
            inputs = {"before": before, "after": after,
                      "map": {**self._map(), "graph": self.store.map_definition.planning_context(),
                              "projected_before": self._image_geometry(binding["server_action"]["drawing_geometry"], before),
                              "projected_after": self._image_geometry(binding["server_action"]["drawing_geometry"], after)},
                      "server_action": binding["server_action"],
                      "expected_visual": payload["expected_visual"]}
            with self.store._lock, self.store._db:
                self._inputs_selected(payload["request_id"], expected_visual=payload["expected_visual"],
                                      image_grounding=inputs["map"])
            result = validate_action(await asyncio.wait_for(self.reviewer.action(inputs), self.timeout))
            evidence = {"id": uuid4().hex, "request_id": payload["request_id"], "source": "meta", "model": MODEL,
                        "input_kind": "server_bound_live_pair", "simulation_only": True, "motion_authority": False,
                        "prompt_version": ACTION_PROMPT_VERSION, "schema_version": ACTION_SCHEMA_VERSION,
                        **binding, "before": before["metadata"], "after": after["metadata"],
                        "expected_visual": payload["expected_visual"], **result,
                        "elapsed_ms": round((time.monotonic()-started)*1000)}
            with self.store._lock, self.store._db:
                state = self.store._load()
                if state["revision"] != binding["workspace_revision"] or self._action_binding(state) != {key: binding[key] for key in self._action_binding(state)}:
                    raise CommandError("The action review was superseded.")
                self.camera.check_binding(after["metadata"])
                state["review"].update(source="meta", verdict=result["verdict"], observed=result["observed"], summary=result["summary"], evidence=evidence)
                self.store._finish_review(state, result["verdict"])
                self.store._event(state, "LIVE_ACTION_REVIEW", f"MUSE live review: {result['verdict']}", result["summary"], "meta", record=evidence)
                # A prior manual GREEN must not bypass the dedicated post-stop query.
                if state["state"] == "WAITING_SIGNAL":
                    state["signal"] = self.store._empty_signal()
                state["revision"] += 1
                self.store._save(state)
                return self._finish(payload["request_id"], self.store._snapshot(state), 200, evidence)
        except SceneError as error:
            if error.code.startswith("MUSE_"):
                return self._fail(payload["request_id"], "MUSE live action review is unavailable. No verdict was applied.", 503 if error.status_code == 503 else 502, evidence)
            return self._fail(payload["request_id"], "Live review input or execution context changed. No verdict was applied.", 409, evidence)
        except CommandError:
            return self._fail(payload["request_id"], "Live review input or execution context changed. No verdict was applied.", 409, evidence)
        except asyncio.CancelledError:
            self._fail(payload["request_id"], "Live action review was interrupted. No verdict was applied.", 503, evidence)
            raise
        except Exception:
            return self._fail(payload["request_id"], "MUSE live action review failed. No demo verdict was substituted.", 502, evidence)

    def reobserve(self, payload):
        kind = "live-reobserve"
        with self.store._lock, self.store._db:
            prior = self._prior(kind, payload)
            if prior:
                return prior
            state = self.store._load()
            self._check_revision(state, payload)
            if state["state"] != "REOBSERVE":
                raise CommandError("A new observation is allowed only after an uncertain review.")
            row = self.store._db.execute("SELECT binding FROM live_action_contexts WHERE review_id=?", (state["review"]["id"],)).fetchone()
            if not row or json.loads(row["binding"])["boot"] != self.boot:
                raise CommandError("The original live action capture is unavailable.")
            captured = json.loads(row["binding"])
            self.store._new_review(state)
            captured.update(self._action_binding(state))
            self.store._db.execute("INSERT INTO live_action_contexts(review_id,binding) VALUES(?,?)", (state["review"]["id"], json.dumps(captured)))
            state["revision"] += 1
            self.store._save(state)
            self._reserve(kind, payload, {"review_id": state["review"]["id"]})
            return self._finish(payload["request_id"], self.store._snapshot(state), 200)

    def _stop_binding(self, state):
        self.store._require_current_map(state)
        self.require_current_live_view(state)
        if (state["mode"] != "simulation" or state["state"] != "WAITING_SIGNAL" or not state["approved"] or not state["stopped"]
                or self.store._kind(state) != "STOP" or state["review"]["verdict"] != "PASS"):
            raise CommandError("A matching accepted simulated full-stop review is required before asking MUSE for a signal.")
        step = state["plan"]["steps"][state["current_step"]]
        receipt = state.get("stop_receipt")
        if not receipt or receipt["action_id"] != step["id"] or receipt["source"] != "simulation":
            raise CommandError("No matching server stop receipt exists.")
        route = state["plan"]["route"]
        index = route["node_ids"].index(step["node_id"])
        approach = route["node_ids"][index-1]
        target = self.store.map_definition.signal_target(step["node_id"], approach)
        if target is None:
            raise CommandError("Configure a reviewed signal target for this map junction and approach before live signal judgment.", 422)
        return {"session_id": state["session_id"], "plan_id": state["plan"]["id"], "plan_revision": state["plan"]["revision"],
                "stop_receipt": receipt, "junction_id": step["node_id"], "approach_from": approach,
                "signal_target": target, **self._map()}

    async def review_signal(self, payload):
        kind = "live-signal-reviews"
        with self.store._lock, self.store._db:
            prior = self._prior(kind, payload)
            if prior:
                return prior
            state = self.store._load()
            self._check_revision(state, payload)
            binding = self._stop_binding(state)
            for pending in self.store._db.execute("SELECT binding FROM live_operations WHERE kind=? AND status='pending'", (kind,)):
                if json.loads(pending["binding"])["stop_receipt"]["id"] == binding["stop_receipt"]["id"]:
                    raise CommandError("A signal judgment is already pending for this stop.")
            binding["workspace_revision"] = state["revision"]
            self._reserve(kind, payload, binding)
        evidence = None
        started = time.monotonic()
        try:
            frame = await self._new_frame(not_before=started)
            with self.store._lock, self.store._db:
                frame = self._save_frame(frame)
                self._inputs_selected(payload["request_id"], frame=frame["metadata"],
                                      prompt_version=SIGNAL_PROMPT_VERSION, schema_version=SIGNAL_SCHEMA_VERSION)
            import cv2
            import numpy as np
            x0, y0, x1, y1 = binding["signal_target"]["bounds_mm"]
            corners = np.array([[x0,y0],[x1,y0],[x1,y1],[x0,y1]], dtype=np.float64)
            matrix = np.array(frame["metadata"]["registration"]["homography"], dtype=np.float64)
            projected = cv2.perspectiveTransform(corners.reshape(-1,1,2), matrix).reshape(4,2)
            if not np.isfinite(projected).all() or any(not (0 <= x < frame["metadata"]["width"] and 0 <= y < frame["metadata"]["height"]) for x,y in projected):
                raise CommandError("The configured signal target is outside the current image.")
            target = {**binding["signal_target"], "image_polygon": projected.tolist(), "pixel_frame_id": frame["metadata"]["id"]}
            with self.store._lock, self.store._db:
                self._inputs_selected(payload["request_id"], projected_signal_target=target)
            inputs = {"frame": frame, "map": self._map(), "signal_target": target, "server_stop": binding}
            result = validate_signal_result(await asyncio.wait_for(self.reviewer.signal(inputs), self.timeout))
            evidence = {"id": uuid4().hex, "request_id": payload["request_id"], "source": "meta", "model": MODEL,
                        "input_kind": "post_stop_live_frame", "simulation_only": True, "motion_authority": False,
                        "prompt_version": SIGNAL_PROMPT_VERSION, "schema_version": SIGNAL_SCHEMA_VERSION,
                        **binding, "frame": frame["metadata"], "projected_signal_target": target, **result,
                        "elapsed_ms": round((time.monotonic()-started)*1000)}
            with self.store._lock, self.store._db:
                state = self.store._load()
                if (state["revision"] != binding["workspace_revision"] or self._stop_binding(state) != {key: binding[key] for key in self._stop_binding(state)}
                        or time.monotonic()-started > self.signal_max_age):
                    raise CommandError("The signal judgment expired or was superseded.")
                self.camera.check_binding(frame["metadata"])
                state["signal"] = {"color": result["color"], "source": "meta", "observed_at": self.store._at(),
                                   "junction_id": binding["junction_id"], "evidence": evidence}
                self.store._event(state, "MUSE_SIGNAL_REVIEW", f"MUSE signal: {result['color']}", result["summary"], "meta", record=evidence)
                self.store._maybe_cross(state)
                if state["state"] == "REVIEW_REQUIRED" and self.store._kind(state) == "CROSS":
                    self._bind_action(state, frame)
                state["revision"] += 1
                self.store._save(state)
                return self._finish(payload["request_id"], self.store._snapshot(state), 200, evidence)
        except SceneError as error:
            if error.code.startswith("MUSE_"):
                return self._fail(payload["request_id"], "MUSE signal review is unavailable. Remain stopped.", 503 if error.status_code == 503 else 502, evidence)
            return self._fail(payload["request_id"], "Signal input, stop context or result age is invalid. No crossing was admitted.", 409, evidence)
        except CommandError:
            return self._fail(payload["request_id"], "Signal input, stop context or result age is invalid. No crossing was admitted.", 409, evidence)
        except asyncio.CancelledError:
            self._fail(payload["request_id"], "MUSE signal review was interrupted. No crossing was admitted.", 503, evidence)
            raise
        except Exception:
            return self._fail(payload["request_id"], "MUSE signal review failed. Remain stopped and request a new observation.", 502, evidence)

    async def wait_signal(self, payload):
        """A bounded observation loop; every attempt selects a new post-request frame."""
        kind = "live-signal-wait"
        attempts, interval = payload.get("max_attempts", 3), payload.get("interval_seconds", 2.0)
        if type(attempts) is not int or not 1 <= attempts <= 3 or isinstance(interval, bool) or not isinstance(interval, (int,float)) or not 0.5 <= interval <= 10:
            raise CommandError("Use 1 to 3 signal attempts and a 0.5 to 10 second interval.", 422)
        with self.store._lock, self.store._db:
            prior = self._prior(kind, payload)
            if prior:
                return prior
            state = self.store._load()
            self._check_revision(state, payload)
            binding = self._stop_binding(state)
            for row in self.store._db.execute("SELECT binding FROM live_operations WHERE kind=? AND status='pending'", (kind,)):
                if json.loads(row["binding"])["stop_receipt"]["id"] == binding["stop_receipt"]["id"]:
                    raise CommandError("A bounded signal wait is already active for this stop.")
            self._reserve(kind, payload, binding)
        revision = payload["expected_revision"]
        try:
            for index in range(attempts):
                child = {"request_id": str(uuid5(UUID(payload["request_id"]), f"signal-{index}")), "expected_revision": revision}
                response, status = await self.review_signal(child)
                if status != 200 or response["state"] != "WAITING_SIGNAL":
                    break
                revision = response["revision"]
                if index+1 < attempts:
                    await asyncio.sleep(interval)
            with self.store._lock, self.store._db:
                return self._finish(payload["request_id"], response, status)
        except (CommandError, SceneError):
            return self._fail(payload["request_id"], "The stop context changed during signal waiting. No further observation was sent.", 409)
        except asyncio.CancelledError:
            self._fail(payload["request_id"], "Signal waiting was interrupted. No further crossing was admitted.", 503)
            raise
        except Exception:
            return self._fail(payload["request_id"], "Signal waiting failed. Inspect current state and remain stopped.", 502)
