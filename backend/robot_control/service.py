"""Single-owner commissioning supervisor. Vision failures never terminate receiver heartbeat."""
from __future__ import annotations

import os
from pathlib import Path
import threading
import time

from .gates import GuardError, admit, validate_local_profile
from .legacy import PrewireRejected
from .store import ControlError, Journal, encode


class ProcessLock:
    def __init__(self, path):
        self.path, self.stream = Path(path), None

    def acquire(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = self.path.open("a+b")
        try:
            if os.name == "nt":
                import msvcrt
                if self.path.stat().st_size == 0:
                    self.stream.write(b"0"); self.stream.flush()
                self.stream.seek(0)
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException:
            self.stream.close(); self.stream = None
            raise ControlError("SERVICE_OWNED", "Another control service owns this state directory.") from None

    def close(self):
        if self.stream:
            self.stream.close(); self.stream = None


class RobotService:
    def __init__(self, journal: Journal, backend, *, physical=False, clock=time.time):
        self.journal, self.backend, self.physical, self.clock = journal, backend, physical, clock
        self.lock = threading.RLock()
        self.wake, self.stopping = threading.Event(), threading.Event()
        self.thread = None
        self.owner = ProcessLock(journal.path.with_suffix(".owner.lock"))
        self.worker_error = None

    def start(self):
        self.owner.acquire()
        try:
            self.backend.open()
            self.journal.recover()
            self.stopping.clear()
            self.thread = threading.Thread(target=self._loop, name="robot-command-worker", daemon=True)
            self.thread.start()
        except BaseException:
            self.backend.close(); self.owner.close()
            raise

    def stop(self):
        self.stopping.set(); self.wake.set()
        if self.thread:
            self.thread.join(timeout=2)
        if self.thread and self.thread.is_alive():
            # Keep ownership/resources until the bounded operation exits or the OS
            # releases them. Shutdown is not a robot-stop instruction.
            self.journal.event(None, "shutdown_during_dispatch", {"robot_stop_issued": False})
            return False
        self.backend.close(); self.owner.close()
        return True

    def receiver(self):
        try:
            return self.backend.snapshot()
        except Exception:
            return {"connected": False, "idle": False, "reason": "Receiver status temporarily unavailable."}

    def status(self):
        receiver = self.receiver()
        receiver["session_motion_mode"] = receiver.get("physical_execution", False)
        receiver["physical_execution"] = self.physical and receiver.get("physical_execution", False)
        installation = self.journal.get_meta("installation")
        scope = installation.get("scope", "board") if installation else None
        return {"schema_version": "pushpilot.robot-control.v1", "mode": "physical_commissioning" if self.physical else "mock",
                "armed": self.journal.get_meta("armed", False), "hold": self.journal.get_meta("hold", False),
                "worker_alive": bool(self.thread and self.thread.is_alive()), "worker_error": self.worker_error,
                "hardware_connected": self.physical and receiver.get("connected", False), "receiver": receiver,
                "installation": installation, "installation_scope": scope,
                "permitted_mutations": (["fixed_z_orientation_local_translate"] if scope == "local_base_commissioning"
                                        else ["translate", "profile_update", "qualified_raised_rotation"] if scope == "board" else []),
                "local_scope_qualifies_board_registration": False,
                "permitted_held_mutations": ["local_profile_update"] if scope == "local_base_commissioning" else [],
                "local_profile_refresh_requires": (["disarmed", "hold", "current_review", "fresh_exact_baseline"]
                                                    if scope == "local_base_commissioning" else []),
                "active_commands": self.journal.active(),
                "automatic_replay": False, "hold_is_emergency_stop": False}

    def install(self, value):
        with self.lock, self.journal.transaction():
            if self.journal.active():
                raise ControlError("COMMAND_ACTIVE", "Reconcile the current operation before changing installation.")
            self.journal._meta("installation", value)
            self.journal._meta("armed", False)
            self.journal._meta("latest_observation_id", None)
            self.journal._event(None, "installation_changed_disarmed", value)
        return value

    def arm(self, value):
        with self.lock:
            installation = self.journal.get_meta("installation")
            if not installation or not installation["qualified"] or value["installation_id"] != installation["installation_id"]:
                raise ControlError("INSTALLATION_UNQUALIFIED", "A current measured installation must be qualified first.")
            if self.journal.active():
                raise ControlError("COMMAND_ACTIVE", "Review or reconcile the current operation before arming.")
            probe = {"kind": "inspect_current", "expected_receiver": value["expected_receiver"]}
            try:
                receiver = self.receiver()
                admit(probe, installation, receiver, None, armed=False, now=self.clock())
                if installation.get("scope") == "local_base_commissioning":
                    validate_local_profile(installation, receiver)
            except GuardError as error:
                raise ControlError(error.code, str(error)) from None
            with self.journal.transaction():
                self.journal._meta("armed", True); self.journal._meta("hold", False)
                self.journal._event(None, "commissioning_armed", value)
        self.wake.set()
        return {"armed": True, "installation_id": installation["installation_id"],
                "scope": installation.get("scope", "board"), "local_scope_qualifies_board_registration": False}

    def hold(self, reason):
        with self.lock, self.journal.transaction():
            self.journal._meta("armed", False); self.journal._meta("hold", True)
            self.journal._event(None, "next_command_inhibited", {"reason": reason, "robot_stop_issued": False})
        self.wake.set()
        return {"hold": True, "effect": "inhibit_uncommitted_commands_only", "robot_stop_issued": False,
                "committed_command_may_still_publish_or_execute": True}

    def submit(self, value):
        with self.lock:
            result, _ = self.journal.create(value)
        self.wake.set()
        return result

    def observe(self, value):
        if value["captured_at"] > self.clock() + 1:
            raise ControlError("FUTURE_OBSERVATION", "Observation capture time is in the future.", 422)
        result = self.journal.observation(value)
        self.wake.set()
        return result

    def cancel(self, request_id):
        with self.lock, self.journal.transaction():
            job = self.journal.get(request_id)
            if job["state"] in {"queued", "waiting_observation"}:
                self.journal.db.execute("UPDATE robot_commands SET state='cancelled',cancel_requested=1,updated=? WHERE id=?", (self.clock(), str(request_id)))
            elif job["state"] in {"dispatching", "committed", "running"}:
                self.journal.db.execute("UPDATE robot_commands SET cancel_requested=1 WHERE id=?", (str(request_id),))
                self.journal._meta("armed", False); self.journal._meta("hold", True)
            self.journal._event(str(request_id), "cancel_requested", {"robot_stop_issued": False,
                "committed_command_may_still_publish_or_execute": job["state"] in {"committed", "running"}})
        self.wake.set()
        return self.journal.get(request_id)

    def _event(self, request_id, kind, data):
        with self.lock:
            if kind == "publication_intent":
                job = self.journal.get(request_id)
                if job["cancel_requested"] or self.stopping.is_set() or job["state"] != "dispatching":
                    raise PrewireRejected("Admission was withdrawn before publication.")
                admit(job["payload"], self.journal.get_meta("installation"), self.receiver(), self.journal.get_observation(),
                      armed=self.journal.get_meta("armed", False), held=self.journal.get_meta("hold", False), now=self.clock(),
                      require_profile_binding=self.physical)
                if self.clock() >= job["expires"]:
                    raise PrewireRejected("Admission deadline expired before publication.")
                # Durable admission boundary: after this commit the transport may
                # publish even if HOLD/cancel arrives before its mailbox link.
                with self.journal.transaction():
                    self.journal.db.execute("UPDATE robot_commands SET state='committed',updated=? WHERE id=?", (self.clock(), str(request_id)))
                    self.journal._event(request_id, kind, {**data, "admission_committed": True,
                        "later_hold_cannot_unsend": True})
            elif kind == "published":
                self.journal.update(request_id, "running")
                self.journal.event(request_id, kind, data)
            else:
                self.journal.event(request_id, kind, data)

    def _loop(self):
        while not self.stopping.is_set():
            try:
                jobs = [job for job in self.journal.active() if job["state"] in {"queued", "waiting_observation"}]
                if jobs:
                    self._run(jobs[0])
            except Exception:
                self.worker_error = "Command worker needs reconciliation; no automatic redispatch."
                try:
                    self.journal.set_meta("armed", False)
                    for job in self.journal.active():
                        if job["state"] in {"dispatching", "committed", "running"}:
                            self.journal.update(job["id"], "outcome_unknown", error=self.worker_error)
                except Exception:
                    pass
            self.wake.wait(.15); self.wake.clear()

    def _run(self, job):
        request_id = job["id"]
        with self.lock:
            job = self.journal.get(request_id)
            if job["state"] not in {"queued", "waiting_observation"}:
                return
            if self.clock() >= job["expires"]:
                self.journal.update(request_id, "rejected", error="ADMISSION_EXPIRED")
                return
            observation = self.journal.get_observation()
            try:
                admit(job["payload"], self.journal.get_meta("installation"), self.receiver(), observation,
                      armed=self.journal.get_meta("armed", False), held=self.journal.get_meta("hold", False), now=self.clock(),
                      require_profile_binding=self.physical)
            except GuardError as error:
                next_state = "waiting_observation" if error.retryable else "rejected"
                if job["state"] != next_state or job["error"] != error.code:
                    self.journal.update(request_id, next_state, error=error.code)
                return
            self.journal.update(request_id, "dispatching")
        try:
            receipt = self.backend.execute(job["payload"], lambda kind, data: self._event(request_id, kind, data))
            result = {"source": "receiver" if self.physical else "mock", "physical_execution": self.physical,
                      "robot_receipt": receipt, "robot_completed_at": self.clock(),
                      "before_observation": observation, "vehicle_completion_verified": False}
            self.journal.update(request_id, "awaiting_review" if job["payload"]["purpose"] == "push" else "complete", result=result)
        except GuardError as error:
            self.journal.update(request_id, "waiting_observation" if error.retryable else "rejected", error=error.code)
        except PrewireRejected as error:
            self.journal.update(request_id, "rejected", error=getattr(error, "code", "REJECTED_BEFORE_WIRE"))
        except Exception:
            self.journal.update(request_id, "outcome_unknown", error="Dispatch outcome is unknown. Inspect receiver and reconcile; do not resend.")
            self.journal.set_meta("armed", False)

    def review(self, request_id, value):
        with self.lock, self.journal.transaction():
            previous = self.journal.db.execute("SELECT command_id,payload FROM robot_reviews WHERE id=?", (value["review_id"],)).fetchone()
            if previous:
                if previous[0] != str(request_id) or previous[1] != encode(value):
                    raise ControlError("REVIEW_CONFLICT", "Review ID already binds another result.")
                return self.journal.get(request_id)
            job = self.journal.get(request_id)
            if job["state"] != "awaiting_review":
                raise ControlError("REVIEW_NOT_PENDING", "This command is not awaiting vehicle-outcome review.")
            observation = self.journal.get_observation(value["observation_id"])
            installation = self.journal.get_meta("installation")
            if not observation or not installation:
                raise ControlError("REOBSERVE", "A new bound observation is required.")
            for key in ("installation_id", "map_id", "map_hash", "calibration_id", "camera_epoch", "registration_id"):
                if observation[key] != installation[key]:
                    raise ControlError("OBSERVATION_BINDING", "Observation belongs to a different installation.")
            now, before = self.clock(), (job["result"] or {}).get("before_observation")
            if (observation["captured_at"] < job["result"]["robot_completed_at"]
                or not 0 <= now - observation["captured_at"] <= installation["observation_max_age_seconds"]
                or observation["view_status"] not in {"fixed", "marker_occluded"}
                or (before and (observation["frame_id"] == before["frame_id"] or observation["frame_sha256"] == before["frame_sha256"]))):
                raise ControlError("REOBSERVE", "Use a fresh, different post-action frame from the fixed view.")
            if value["verdict"] == "PASS" and (not observation["car_visible"] or observation.get("car_pose") is None):
                raise ControlError("CAR_OCCLUDED", "Accepting a push requires a visible car and a measured finite car pose.")
            self.journal.db.execute("INSERT INTO robot_reviews VALUES(?,?,?)", (value["review_id"], str(request_id), encode(value)))
            state = "complete" if value["verdict"] == "PASS" else "review_failed" if value["verdict"] == "FAIL" else "awaiting_review"
            self.journal.db.execute("UPDATE robot_commands SET state=?,updated=?,error=? WHERE id=?",
                                    (state, now, None if state == "complete" else value["verdict"], str(request_id)))
            if state == "review_failed":
                self.journal._meta("armed", False); self.journal._meta("hold", True)
            if state == "complete":
                result = {**job["result"], "vehicle_review_accepted": True, "review_source": value["source"],
                          "review_id": value["review_id"], "observation_id": value["observation_id"]}
                self.journal.db.execute("UPDATE robot_commands SET result=? WHERE id=?", (encode(result), str(request_id)))
            self.journal._event(str(request_id), "vehicle_outcome_review", value)
        return self.journal.get(request_id)

    def reconcile(self, request_id, value):
        with self.lock:
            job = self.journal.get(request_id)
            if job["state"] != "outcome_unknown":
                raise ControlError("NOT_UNKNOWN", "Only an unknown dispatch requires this reconciliation.")
            installation = self.journal.get_meta("installation")
            inspection_without_installation = not installation and job["payload"]["kind"] in {"inspect_current", "inspect_ik"}
            if not inspection_without_installation and (not installation or installation["installation_id"] != value["installation_id"]):
                raise ControlError("INSTALLATION_MISMATCH", "Reconciliation must bind the current installation.")
            try:
                admit({"kind": "inspect_current", "expected_receiver": value["expected_receiver"]}, installation,
                      self.receiver(), None, armed=False, now=self.clock())
            except GuardError as error:
                raise ControlError(error.code, str(error)) from None
            with self.journal.transaction():
                self.journal._meta("armed", False)
                self.journal._event(str(request_id), "operator_reconciliation_intent", value)
            # Keep the unknown job blocking new submissions until both the
            # transport latch and durable operator reconciliation are resolved.
            try:
                receipt = self.backend.reconcile(value["expected_receiver"])
            except Exception:
                raise ControlError("RECONCILIATION_BLOCKED", "Receiver is not ready for bound idle reconciliation; inspect the current session.") from None
            with self.journal.transaction():
                self.journal.db.execute("UPDATE robot_commands SET state='reconciled',updated=?,error=? WHERE id=?",
                                        (self.clock(), value["measured_outcome"], str(request_id)))
                self.journal._event(str(request_id), "operator_reconciled_no_replay", {**value, "receiver_receipt": receipt})
        return self.journal.get(request_id)
