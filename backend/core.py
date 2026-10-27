"""Durable symbolic mission supervision, with no hardware or timer-driven motion."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import threading
import time
from typing import Callable
from uuid import uuid4

from backend.meta import GoalProvider, ProviderError

ACTIVE = {"READY", "REVIEW_REQUIRED", "WAITING_SIGNAL", "REOBSERVE"}
STEP_DEFINITIONS = (
    ("PUSH", "Surface push", "One bounded simulated push from symbolic PIZZA."),
    ("STOP", "Mandatory stop", "Verify a simulated full stop before evaluating entry."),
    ("CROSS", "Admitted crossing", "Enter only after an accepted stop review and fresh GREEN."),
    ("VERIFY", "Destination check", "Review the symbolic BAKERY outcome."),
)


class CommandError(Exception):
    def __init__(self, message: str, status: int = 409):
        self.message, self.status = message, status
        super().__init__(message)


class WorkspaceStore:
    """Serialize revisioned commands and append evidence in one SQLite transaction."""

    def __init__(self, db_path: str, *, provider: GoalProvider, muse_configured: bool = False,
                 signal_ttl_seconds: float = 30.0, clock: Callable[[], float] = time.time):
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(db_path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._provider, self._clock = provider, clock
        self._muse_configured = muse_configured
        self._signal_ttl = signal_ttl_seconds
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS workspace (id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events (sequence INTEGER PRIMARY KEY AUTOINCREMENT, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS requests (id TEXT PRIMARY KEY, digest TEXT NOT NULL, status INTEGER NOT NULL, response TEXT NOT NULL);
        """)
        with self._db:
            row = self._db.execute("SELECT value FROM workspace WHERE id=1").fetchone()
            if row is None:
                state = self._empty_state()
                self._event(state, "WORKSPACE_STARTED", "Simulation workspace ready", "No robot, camera, or registered AR is connected.", "simulation")
                self._save(state)
            else:
                state = json.loads(row["value"])
                if state["state"] in ACTIVE:
                    state.update(state="RECOVERY_REQUIRED", approved=False, stopped=False, review=None)
                    state["signal"] = self._empty_signal()
                    state["revision"] += 1
                    self._event(state, "RESTART_RECOVERY", "Recovery required after restart", "Previous approval, stop verification, and signal authority were cleared. Explicit reset is required; no command was replayed.", "simulation")
                    self._save(state)
                elif state["signal"]["observed_at"] is not None:
                    state["signal"] = self._empty_signal()
                    state["revision"] += 1
                    self._event(state, "SIGNAL_CLEARED", "Signal cleared after restart", "A previous observation cannot authorize a new entry.", "simulation")
                    self._save(state)

    def close(self) -> None:
        self._db.close()

    def _at(self) -> str:
        return datetime.fromtimestamp(self._clock(), timezone.utc).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _empty_signal() -> dict:
        return {"color": "UNKNOWN", "source": "simulation", "observed_at": None}

    def _empty_state(self) -> dict:
        return {"schema_version": "pushpilot.workspace.v1", "session_id": str(uuid4()), "revision": 0,
                "state": "IDLE", "mode": "simulation", "goal": None, "plan": None,
                "current_step": 0, "approved": False, "stopped": False,
                "signal": self._empty_signal(), "review": None}

    def _load(self) -> dict:
        return json.loads(self._db.execute("SELECT value FROM workspace WHERE id=1").fetchone()["value"])

    def _save(self, state: dict) -> None:
        self._db.execute("INSERT INTO workspace(id,value) VALUES(1,?) ON CONFLICT(id) DO UPDATE SET value=excluded.value", (json.dumps(state),))

    def _event(self, state: dict, kind: str, title: str, detail: str, source: str) -> None:
        event = {"id": str(uuid4()), "at": self._at(), "kind": kind, "title": title,
                 "detail": detail, "source": source, "state": state["state"]}
        self._db.execute("INSERT INTO events(value) VALUES(?)", (json.dumps(event),))

    def _snapshot(self, state: dict) -> dict:
        result = deepcopy(state)
        result["next_check"] = self._next_check(state)
        result["capabilities"] = {"robot": False, "camera": False, "registered_ar": False,
                                  "muse_configured": self._muse_configured, "voice": False, "image_review": False}
        result["events"] = [{**json.loads(row["value"]), "sequence": row["sequence"]}
                            for row in self._db.execute("SELECT sequence,value FROM events ORDER BY sequence")]
        return result

    def snapshot(self) -> dict:
        with self._lock:
            return self._snapshot(self._load())

    def _next_check(self, state: dict) -> str:
        return {
            "IDLE": "Enter a goal for symbolic BAKERY.",
            "PLAN_READY": "Review and explicitly approve this plan revision.",
            "READY": "Run the next bounded simulated action.",
            "REVIEW_REQUIRED": "Submit an explicitly demo-sourced verdict for this observation.",
            "WAITING_SIGNAL": "Wait for a fresh simulated GREEN. An accepted stop review is already recorded.",
            "REOBSERVE": "Create a new simulated observation and review; no motion will run.",
            "COMPLETED": "Mission complete in simulation. Reset before a new goal.",
            "CANCELLED": "Mission cancelled. Reset before a new goal.",
            "FAULT": "Review the failure evidence and reset explicitly.",
            "RECOVERY_REQUIRED": "Inspect the prior evidence and reset explicitly. Execution will not resume.",
        }[state["state"]]

    def execute(self, action: str, payload: dict) -> tuple[dict, int]:
        digest = hashlib.sha256(json.dumps({"action": action, "payload": payload}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        with self._lock, self._db:
            prior = self._db.execute("SELECT * FROM requests WHERE id=?", (payload["request_id"],)).fetchone()
            if prior:
                if prior["digest"] != digest:
                    raise CommandError("This request ID is already bound to a different command.")
                # Return the original receipt, including its original revision.
                return json.loads(prior["response"]), prior["status"]
            state = self._load()
            if payload["expected_revision"] != state["revision"]:
                raise CommandError("Workspace changed. Refresh state before submitting this command.")
            try:
                self._apply(state, action, payload)
                status = 200
            except ProviderError as error:
                # A failed replacement must not leave an older plan approvable.
                state.update(state="IDLE", goal=None, plan=None, current_step=0,
                             approved=False, stopped=False, review=None)
                state["signal"] = self._empty_signal()
                self._event(state, "PROVIDER_FAILED", "MUSE interpretation unavailable", str(error), "meta")
                status = 502
            state["revision"] += 1
            self._save(state)
            response = self._snapshot(state) if status == 200 else {"detail": "MUSE goal interpretation failed. No plan was created."}
            self._db.execute("INSERT INTO requests(id,digest,status,response) VALUES(?,?,?,?)",
                             (payload["request_id"], digest, status, json.dumps(response)))
            return response, status

    def _apply(self, state: dict, action: str, payload: dict) -> None:
        if action == "goals":
            self._goal(state, payload)
        elif action == "approve":
            if state["state"] != "PLAN_READY" or not state["plan"]:
                raise CommandError("There is no plan awaiting approval.")
            if payload["plan_id"] != state["plan"]["id"] or payload["plan_revision"] != state["plan"]["revision"]:
                raise CommandError("Approval does not match the current plan revision.")
            state.update(state="READY", approved=True)
            state["plan"]["steps"][0]["status"] = "current"
            self._event(state, "PLAN_APPROVED", "Plan approved", "The operator approved this symbolic simulation plan only.", "operator")
        elif action == "advance":
            if state["state"] != "READY" or not state["approved"]:
                raise CommandError("The next action is inhibited until approval and the required review.")
            if self._kind(state) == "CROSS":
                raise CommandError("Crossing admission is owned by the stop and signal gate.")
            self._run_step(state)
        elif action == "signal":
            if state["state"] not in ACTIVE | {"IDLE", "PLAN_READY"}:
                raise CommandError("Signal input is unavailable in this mission state.")
            state["signal"] = {"color": payload["color"], "source": "simulation", "observed_at": self._at()}
            self._event(state, "SIGNAL_OBSERVED", f"Simulated signal: {payload['color']}", "Operator-injected simulation observation; this is not camera detection.", "simulation")
            if state["state"] == "WAITING_SIGNAL":
                self._maybe_cross(state)
        elif action == "reviews":
            self._review(state, payload)
        elif action == "reobserve":
            if state["state"] != "REOBSERVE":
                raise CommandError("A new observation is permitted only after an uncertain review.")
            self._new_review(state)
            self._event(state, "REOBSERVED", "New simulated observation", "The previous review binding was replaced. No movement was executed.", "simulation")
        elif action == "cancel":
            if state["state"] not in ACTIVE | {"PLAN_READY", "RECOVERY_REQUIRED"}:
                raise CommandError("There is no active mission to cancel.")
            state.update(state="CANCELLED", approved=False)
            self._event(state, "MISSION_CANCELLED", "Simulation cancelled", "No further simulated action is admitted. This command is not a hardware emergency stop.", "operator")
        elif action == "reset":
            if state["state"] in ACTIVE:
                raise CommandError("Cancel the active mission before resetting it.")
            session, revision = state["session_id"], state["revision"]
            state.clear()
            state.update(self._empty_state(), session_id=session, revision=revision)
            self._event(state, "WORKSPACE_RESET", "Workspace reset", "Plan, approval, review, stop, and signal bindings were cleared. Evidence history was retained.", "operator")
        else:
            raise CommandError("Unknown workspace command.", 404)

    def _goal(self, state: dict, payload: dict) -> None:
        if payload.get("source") == "voice":
            raise CommandError("Voice transcription is not implemented. Use typed input for this milestone.", 422)
        if state["state"] not in {"IDLE", "PLAN_READY"}:
            raise CommandError("Reset a completed or terminated mission before submitting a new goal.")
        text = payload["text"].strip()
        if not text:
            raise CommandError("Enter a nonempty goal.", 422)
        if payload["provider"] == "meta":
            result = self._provider.interpret(text)
            if (not isinstance(result, dict) or result.get("destination") not in {"BAKERY", "UNKNOWN"}
                    or type(result.get("requires_clarification")) is not bool
                    or not isinstance(result.get("summary"), str)
                    or not 1 <= len(result["summary"]) <= 500):
                raise ProviderError("MUSE returned an invalid goal interpretation.")
        else:
            destination_known = any(word in text.casefold() for word in ("bakery", "빵집", "베이커리"))
            result = {"destination": "BAKERY" if destination_known else "UNKNOWN",
                      "summary": "Push the wheel-less car from PIZZA to symbolic BAKERY." if destination_known else "Please specify BAKERY for this prototype.",
                      "requires_clarification": not destination_known}
        if result["requires_clarification"] or result["destination"] != "BAKERY":
            state.update(state="IDLE", goal=None, plan=None, approved=False, review=None, stopped=False, current_step=0)
            state["signal"] = self._empty_signal()
            self._event(state, "GOAL_CLARIFICATION", "Goal needs clarification", result["summary"], payload["provider"])
            return
        state.update(state="PLAN_READY", approved=False, stopped=False, review=None, current_step=0)
        state["signal"] = self._empty_signal()
        state["goal"] = {"text": text, "destination": "BAKERY", "summary": result["summary"],
                         "source": payload.get("source", "typed"), "provider": payload["provider"]}
        state["plan"] = {"id": str(uuid4()), "revision": state["revision"] + 1,
                         "steps": [{"id": str(uuid4()), "kind": kind, "label": label, "description": description, "status": "pending"}
                                   for kind, label, description in STEP_DEFINITIONS]}
        self._event(state, "GOAL_INTERPRETED", "Symbolic plan prepared", result["summary"], payload["provider"])

    @staticmethod
    def _kind(state: dict) -> str:
        return state["plan"]["steps"][state["current_step"]]["kind"]

    def _new_review(self, state: dict) -> None:
        kind = self._kind(state)
        state["state"] = "REVIEW_REQUIRED"
        state["review"] = {"id": str(uuid4()), "verdict": "PENDING", "source": "demo",
                           "expected": f"Confirm the simulated {kind.lower()} outcome.",
                           "observed": "Symbolic simulation result; no image or hardware receipt was captured.",
                           "summary": "Awaiting an explicitly demo-sourced verdict."}

    def _run_step(self, state: dict) -> None:
        kind = self._kind(state)
        if kind == "STOP":
            state["stopped"] = True
        self._new_review(state)
        self._event(state, "SIMULATED_ACTION_COMPLETED", f"Simulated {kind.lower()} completed",
                    "Mandatory simulated full stop recorded before entry." if kind == "STOP" else "A bounded abstract action completed in simulation. This is not physical-execution evidence.", "simulation")

    def _review(self, state: dict, payload: dict) -> None:
        if state["state"] != "REVIEW_REQUIRED" or not state["review"] or state["review"]["id"] != payload["review_id"]:
            raise CommandError("The review does not match the current pending observation.")
        verdict = payload["verdict"]
        state["review"].update(verdict=verdict, summary=f"Operator-injected demo verdict: {verdict}. No MUSE image review was called.")
        if verdict == "FAIL":
            state.update(state="FAULT", approved=False)
        elif verdict in {"UNKNOWN", "REOBSERVE"}:
            state["state"] = "REOBSERVE"
        else:
            kind = self._kind(state)
            state["plan"]["steps"][state["current_step"]]["status"] = "complete"
            if kind == "STOP":
                state["state"] = "WAITING_SIGNAL"
            elif kind == "VERIFY":
                state.update(state="COMPLETED", approved=False)
            else:
                state["current_step"] += 1
                state["plan"]["steps"][state["current_step"]]["status"] = "current"
                state["state"] = "READY"
        self._event(state, "DEMO_REVIEW_RECORDED", f"Demo review: {verdict}", state["review"]["summary"], "demo")
        if state["state"] == "WAITING_SIGNAL":
            self._maybe_cross(state)

    def _maybe_cross(self, state: dict) -> None:
        review = state["review"]
        if not (state["approved"] and state["stopped"] and self._kind(state) == "STOP"
                and review and review["verdict"] == "PASS" and state["signal"]["color"] == "GREEN"):
            return
        observed_at = state["signal"]["observed_at"]
        if not observed_at:
            return
        observed_seconds = datetime.fromisoformat(observed_at.replace("Z", "+00:00")).timestamp()
        age = self._clock() - observed_seconds
        if not 0 <= age <= self._signal_ttl:
            self._event(state, "SIGNAL_STALE", "Fresh GREEN required", "The simulation observation expired. The demonstration TTL is not a qualified physical tolerance.", "simulation")
            return
        state["current_step"] = 2
        state["plan"]["steps"][2]["status"] = "current"
        self._event(state, "CROSSING_ADMITTED", "Simulated crossing admitted", "Accepted stop review and a fresh simulated GREEN admitted one bounded crossing. Later signal changes apply to the next entry.", "simulation")
        self._run_step(state)
