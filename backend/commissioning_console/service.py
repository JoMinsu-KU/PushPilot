"""Durable one-unit commissioning sessions, separate from product missions.

The product broker and the SAME OS journal lock fence the two executors. A
browser disconnect never advances a route; request IDs never replay a unit.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3
import threading
import time
from uuid import UUID, uuid4

from backend.robot_control.service import ProcessLock
from backend.robot_control.taught_executor import ExecutionBlocked
from backend.robot_control.taught_ports import encoded, private_directory


class ConsoleError(Exception):
    def __init__(self, code, message, status=409):
        self.code, self.message, self.status = code, message, status
        super().__init__(message)


def require(value, code, message):
    if not value:
        raise ConsoleError(code, message)


class ConsoleService:
    def __init__(self, config_file, state_dir, *, adapter=None):
        if adapter is None:
            from .adapter import ConsoleAdapter
            adapter = ConsoleAdapter(config_file)
        self.adapter = adapter
        self.root = private_directory(state_dir)
        self.process_owner = ProcessLock(self.root / "console.owner.lock")
        self.process_owner.acquire()
        self.db = sqlite3.connect(self.root / "console.sqlite3", check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            PRAGMA synchronous=FULL;
            CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS requests (id TEXT PRIMARY KEY, digest TEXT NOT NULL, result TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, at REAL NOT NULL, kind TEXT NOT NULL, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS drafts (id TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS reservations (request_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, state TEXT NOT NULL);
        """)
        self.lock = threading.RLock()
        self.stop_request_lock = threading.Lock()
        self.pending_stops = {}
        self.request_cache = {r["id"]: (r["digest"], json.loads(r["result"]))
                              for r in self.db.execute("SELECT * FROM requests")}
        self.thread = None
        self.stop_event = threading.Event()
        self.owner_lock = None
        saved = self.db.execute("SELECT value FROM state WHERE id=1").fetchone()
        self.data = json.loads(saved[0]) if saved else {"revision": 0, "state": "READ_ONLY", "run": None,
            "last_operation": None, "draft": None, "owner_id": None, "error": None}
        uncertain = self.db.execute("SELECT * FROM reservations WHERE state='PENDING' ORDER BY rowid DESC LIMIT 1").fetchone()
        if uncertain:
            self.data.update(state="RECONCILIATION_REQUIRED", owner_id=uncertain["owner_id"],
                error="BROKER_RESERVATION_OUTCOME_UNRESOLVED", broker_request_id=uncertain["request_id"])
        # Restarting a process is never authority to adopt a prior owner or
        # resubmit a request. Retain all old rows and fail closed.
        if self.data.get("owner_id") or self.data["state"] in {"RUNNING", "OBSERVING", "ACQUIRING", "RELEASING"}:
            self.data["state"] = "RECONCILIATION_REQUIRED"
            self.data["error"] = "CONSOLE_RESTART_RECONCILIATION_REQUIRED"
            self._persist()

    def _persist(self):
        self.db.execute("INSERT OR REPLACE INTO state VALUES (1,?)", (encoded(self.data).decode(),))
        self.db.commit()

    def _event(self, kind, value):
        self.db.execute("INSERT INTO events(at,kind,value) VALUES(?,?,?)", (time.time(), kind, encoded(value).decode()))

    def _revision(self):
        self.data["revision"] += 1
        self._persist()

    def _owned(self):
        require(self.owner_lock is not None, "PRODUCTION_EXECUTOR_OWNS_ROBOT", "시험 제어권을 먼저 인계받아야 합니다.")

    def _idle(self):
        require(not self.thread or not self.thread.is_alive(), "CONSOLE_BUSY", "현재 단계가 끝날 때까지 기다려 주세요.")

    def _request(self, kind, value, action):
        request_id = value.get("request_id")
        try:
            require(str(UUID(request_id)) == request_id, "REQUEST_ID_REQUIRED", "새 UUID 요청 식별자가 필요합니다.")
        except (ValueError, TypeError, AttributeError):
            raise ConsoleError("REQUEST_ID_REQUIRED", "새 UUID 요청 식별자가 필요합니다.", 422) from None
        digest = hashlib.sha256(encoded({"kind": kind, "value": value})).hexdigest()
        with self.lock:
            prior = self.db.execute("SELECT * FROM requests WHERE id=?", (request_id,)).fetchone()
            if prior:
                require(prior["digest"] == digest, "REQUEST_ID_REUSED", "같은 ID로 다른 요청을 보낼 수 없습니다.")
                return json.loads(prior["result"])
            if kind != "stop":
                require(type(value.get("expected_revision")) is int and value["expected_revision"] == self.data["revision"],
                        "REVISION_CHANGED", "상태를 새로 확인한 후 다시 선택해 주세요.")
            result = action()
            result = {**result, "request_id": request_id, "revision": self.data["revision"]}
            self.db.execute("INSERT INTO requests VALUES(?,?,?)", (request_id, digest, encoded(result).decode()))
            self.db.commit()
            self.request_cache[request_id] = (digest, deepcopy(result))
            return result

    def routes(self):
        return self.adapter.routes()

    def _step(self, route, step_id):
        matches = [s for r in self.routes()["routes"] if r["code"] == route
                   for s in [*r["steps"], *r.get("empty_return", [])] if s["id"] == step_id]
        require(len(matches) == 1, "STEP_NOT_FOUND", "등록된 코스와 단계를 선택해 주세요.")
        return matches[0]

    def status(self):
        try:
            passive = self.adapter.passive_status()
            receiver = passive.get("robot", {}).get("receiver", {})
            robot = {"connected": receiver.get("connected", False), "stationary": receiver.get("idle", False),
                "tcp_base": receiver.get("actual_pose"), "session_id": receiver.get("session_id"),
                "sequence": receiver.get("seq"), "reason": receiver.get("reason"),
                "physical_state": passive.get("physical", {}).get("state")}
        except Exception:
            robot = {"connected": False, "stationary": False, "reason": "STATUS_UNAVAILABLE"}
        with self.lock:
            result = deepcopy(self.data)
            result["robot"] = robot
            result["ownership"] = {"owned": self.owner_lock is not None,
                "blockers": [] if self.owner_lock else ["PRODUCTION_EXECUTOR_OWNS_ROBOT"]}
            result["history"] = [{**dict(r), "value": json.loads(r["value"])} for r in
                reversed(self.db.execute("SELECT * FROM events ORDER BY id DESC LIMIT 80").fetchall())]
            result["mode"] = "commissioning"  # Never a released product mission.
            return result

    def acquire(self, value):
        def action():
            self._idle()
            require(self.data["state"] == "READ_ONLY", "SESSION_NOT_RELEASED", "이전 시험의 미해결 상태를 먼저 확인해 주세요.")
            require(self.owner_lock is None, "ALREADY_OWNED", "이미 시험 제어권을 보유하고 있습니다.")
            owner_id = "console-" + uuid4().hex
            # Broker rejection performs no robot HOLD/profile/command IO.
            self.db.execute("INSERT INTO reservations VALUES(?,?,'PENDING')", (value["request_id"], owner_id))
            self.db.commit()  # Preserve identity BEFORE the ownership POST.
            try:
                self.adapter.reserve(owner_id, "Operator requests an exclusive one-unit commissioning session.",
                                     request_id=value["request_id"])
            except Exception as error:
                if getattr(error, "broker_rejected", False) or isinstance(error, ConsoleError):
                    self.db.execute("UPDATE reservations SET state='REJECTED' WHERE request_id=?", (value["request_id"],))
                    self.db.commit()
                else:
                    self.data.update(state="RECONCILIATION_REQUIRED", owner_id=owner_id,
                        error="BROKER_RESERVATION_OUTCOME_UNRESOLVED", broker_request_id=value["request_id"])
                    self._revision()
                raise
            self.db.execute("UPDATE reservations SET state='RESERVED' WHERE request_id=?", (value["request_id"],))
            self.db.commit()
            production = Path(self.adapter.production_journal_root)
            lease = ProcessLock(production / "runner.owner.lock")
            try:
                lease.acquire()
            except Exception:
                # Do not force-unlock, stop the product, or invent a successful
                # rollback when another owner still holds the lock.
                self.data.update(state="RECONCILIATION_REQUIRED", owner_id=owner_id, error="EXECUTOR_OWNERSHIP_CONFLICT")
                self._revision()
                raise ConsoleError("EXECUTOR_OWNERSHIP_CONFLICT", "제어권 인계가 완료되지 않았습니다. 기존 실행자를 확인해 주세요.") from None
            self.owner_lock = lease
            self.data.update(state="ACQUIRING", owner_id=owner_id, error=None)
            self._event("ownership_reserved", {"owner_id": owner_id})
            self._revision()  # Durable before profile/Native preparation.
            try:
                self.adapter.acquire(self.root / ("session-" + owner_id))
            except Exception as error:
                code = getattr(error, "code", "ACQUISITION_" + type(error).__name__.upper())
                self.data.update(state="RECONCILIATION_REQUIRED", error=code)
                self._event("acquisition_failed", {"code": code, "error_type": type(error).__name__,
                    "motion_dispatched": False, "owner_id": owner_id})
                self._revision()
                raise
            self.data.update(state="READY", run=None, last_operation=None)
            self._revision()
            return {"accepted": True, "owner_id": owner_id}
        return self._request("acquire", value, action)

    def release(self, value):
        def action():
            self._owned(); self._idle()
            require(self.data["state"] in {"READY", "REVIEW_REQUIRED"}, "RECONCILIATION_REQUIRED", "미확정 이동이 있으면 제어권을 해제할 수 없습니다.")
            self.adapter.ready_to_release()  # Independent exact common START.
            owner_id = self.data["owner_id"]
            self.data["state"] = "RELEASING"
            self._revision()
            self.adapter.close()
            self.owner_lock.close()
            self.owner_lock = None
            self.adapter.release_reservation(owner_id, "Commissioning ended at the independently verified original START.")
            self._event("ownership_released", {"owner_id": owner_id})
            self.data.update(state="READ_ONLY", owner_id=None, error=None)
            self._revision()
            return {"accepted": True}
        return self._request("release", value, action)

    def draft(self, value):
        def action():
            self._idle()
            require(self.data["state"] not in {"RECONCILIATION_REQUIRED", "ACQUIRING", "RELEASING"}, "RECONCILIATION_REQUIRED", "먼저 미확정 결과를 확인해 주세요.")
            step = self._step(value.get("route"), value.get("step_id"))
            draft = self.adapter.validate_draft(step, value)
            draft.update(id="draft-" + uuid4().hex, route=value["route"], step_id=value["step_id"], approved=False)
            self.db.execute("INSERT INTO drafts VALUES(?,?)", (draft["id"], encoded(draft).decode()))
            self._event("draft_created", {"draft_id": draft["id"], "geometry_sha256": draft["geometry_sha256"]})
            self.data["draft"] = draft
            self._revision()
            return {"draft": draft}
        return self._request("draft", value, action)

    def approve(self, draft_id, value):
        def action():
            self._idle()
            reason = value.get("reason", "")
            require(isinstance(reason, str) and 10 <= len(reason) <= 500, "REVIEW_REASON_REQUIRED", "경로와 공구 전체 여유를 확인한 검토 사유를 입력해 주세요.")
            row = self.db.execute("SELECT value FROM drafts WHERE id=?", (draft_id,)).fetchone()
            require(row is not None, "DRAFT_NOT_FOUND", "저장된 수정안을 선택해 주세요.")
            draft = json.loads(row[0])
            require(not draft["approved"], "DRAFT_ALREADY_APPROVED", "승인된 수정안은 변경할 수 없습니다.")
            reviewed = value.get("reviewed_fields")
            required = draft.get("required_reviewed_fields", [])
            require(isinstance(reviewed, list) and reviewed == required and len(required) >= 5,
                    "EXPLICIT_DRAFT_REVIEW_REQUIRED", "고정 자세·공구 여유·접촉 해제·연속성·허용 영역을 모두 확인해 주세요.")
            draft.update(approved=True, approval={"at": time.time(), "reason": reason, "request_id": value["request_id"],
                "scope": "current_site_experiment_only", "approved": True, "repeatability_qualified": False,
                "geometry_sha256": draft["geometry_sha256"], "reviewed_fields": reviewed,
                "contact_normal_base_xy": draft.get("required_contact_normal_base_xy")})
            self.db.execute("UPDATE drafts SET value=? WHERE id=?", (encoded(draft).decode(), draft_id))
            self.data["draft"] = draft
            self._event("draft_reviewed", {"draft_id": draft_id, "approval": draft["approval"]})
            self._revision()
            return {"draft": draft}
        return self._request("approve", value, action)

    def execute(self, value):
        def action():
            self._owned(); self._idle()
            require(self.data["state"] == "READY", "REVIEW_OR_RECONCILIATION_REQUIRED", "이전 결과 검토가 완료되어야 다음 단계를 실행할 수 있습니다.")
            step = self._step(value.get("route"), value.get("step_id"))
            draft = None
            if value.get("draft_id"):
                row = self.db.execute("SELECT value FROM drafts WHERE id=?", (value["draft_id"],)).fetchone()
                require(row is not None, "DRAFT_NOT_FOUND", "수정안을 찾을 수 없습니다.")
                draft = json.loads(row[0])
                require(draft["approved"] is True and (draft["route"], draft["step_id"]) == (value["route"], value["step_id"]),
                        "DRAFT_REVIEW_REQUIRED", "이 단계의 정확한 수정안을 먼저 검토 승인해 주세요.")
            self.stop_event.clear()
            previous_run = deepcopy(self.data.get("run"))
            self.data.update(state="RUNNING", error=None, run={"route": value["route"], "step_id": value["step_id"],
                "command_id": value["request_id"], "draft_id": value.get("draft_id"), "phase": "PREPARING",
                "before_artifact_id": None, "after_artifact_id": None, "review": None})
            self.data["last_operation"] = {"id": value["request_id"], "kind": "execute", "state": "ACCEPTED"}
            self._event("unit_requested", {"request": value, "draft": draft})
            self._revision()  # Intent stored before the worker exists.
            self.thread = threading.Thread(target=self._execute_worker, args=(deepcopy(value), draft, previous_run), name="commissioning-unit", daemon=False)
            self.thread.start()
            return {"accepted": True, "operation_id": value["request_id"]}
        return self._request("execute", value, action)

    def _execute_worker(self, value, draft, previous_run=None):
        try:
            receipt = self.adapter.execute(value["route"], value["step_id"], draft, value["request_id"])
            with self.lock:
                self.data["run"].update(phase="NATIVE_COMPLETE", receipt=receipt,
                    before_artifact_id=receipt.get("before_artifact_id"), after_artifact_id=receipt.get("after_artifact_id"))
                self._event("unit_native_complete", receipt)
                self.data["last_operation"]["state"] = "COMPLETED"
                self.data["state"] = "REVIEW_REQUIRED"
                self._revision()
            # Review is a separate operation, automatically requested only
            # after the WHOLE unit has withdrawn. Never mid-contact vision.
            if not self.stop_event.is_set():
                self._observe_worker()
        except Exception as error:
            with self.lock:
                code = getattr(error, "code", "UNIT_OUTCOME_UNRESOLVED")
                if getattr(error, "known_before_execute", False) is True:
                    self.data.update(state="REVIEW_REQUIRED" if previous_run else "READY", error=code, run=previous_run)
                    if previous_run and code == "CONSOLE_SIGNAL_GREEN_REQUIRED" and previous_run.get("signal_gate"):
                        previous_run["signal_gate"]["accepted"] = False
                    self.data["last_operation"]["state"] = "REJECTED_UNSENT"
                    self._event("unit_selection_rejected", {"code": code, "command_id": value["request_id"], "motion_dispatched": False})
                    self._revision()
                    return
                self.data.update(state="RECONCILIATION_REQUIRED", error=code)
                self.data["run"]["phase"] = "STOPPED_RECONCILE"
                self.data["last_operation"]["state"] = "UNRESOLVED"
                self._event("unit_interrupted", {"code": code, "command_id": value["request_id"], "automatic_retry": False})
                self._revision()

    def _observe_worker(self):
        try:
            with self.lock:
                self.data["state"] = "OBSERVING"
                self.data["run"]["phase"] = "MUSE_REVIEW"
                self._revision()
            result = self.adapter.observe()
            with self.lock:
                self.data["run"].update(result)
                self.data["run"]["phase"] = "REVIEWED"
                self.data["state"] = "REVIEW_REQUIRED"  # Explicit next-unit selection even after PASS.
                self._event("unit_reviewed", result)
                self._revision()
        except Exception as error:
            with self.lock:
                self.data.update(state="REVIEW_REQUIRED", error=getattr(error, "code", "OBSERVATION_FAILED"))
                self.data["run"]["phase"] = "REOBSERVATION_AVAILABLE"
                self._event("review_failed", {"code": self.data["error"], "motion_replayed": False})
                self._revision()

    def observe(self, value):
        def action():
            self._owned(); self._idle()
            require(self.data["state"] == "REVIEW_REQUIRED" and self.data["run"], "COMPLETED_UNIT_REQUIRED", "완료된 이동의 관측만 다시 요청할 수 있습니다.")
            self.data["state"] = "OBSERVING"
            self._event("reobservation_requested", value)
            self._revision()
            self.thread = threading.Thread(target=self._observe_worker, name="commissioning-observe", daemon=False)
            self.thread.start()
            return {"accepted": True}
        return self._request("observe", value, action)

    def acknowledge(self, value):
        def action():
            self._owned(); self._idle()
            require(self.data["state"] == "REVIEW_REQUIRED", "REVIEW_REQUIRED", "완료된 결과를 먼저 확인해 주세요.")
            gate = (self.data.get("run") or {}).get("signal_gate")
            require(not gate or gate.get("accepted") is True, "SIGNAL_GREEN_REQUIRED", "신호 대기에서는 실제 GREEN 관측이 필요합니다.")
            reason = value.get("reason", "")
            require(isinstance(reason, str) and 10 <= len(reason) <= 500, "REVIEW_REASON_REQUIRED", "관측 결과와 다음 시험 사유를 기록해 주세요.")
            self.adapter.confirm_stationary()  # A model verdict cannot clear unknown motion.
            self._event("operator_review_acknowledged", {"reason": reason, "run": self.data["run"],
                "model_verdict_overwritten": False, "qualification_granted": False})
            self.data.update(state="READY", error=None)
            self._revision()
            return {"accepted": True}
        return self._request("acknowledge", value, action)

    def signal(self, value):
        def action():
            self._owned(); self._idle()
            run = self.data.get("run")
            require(self.data["state"] == "REVIEW_REQUIRED" and run and run.get("signal_gate"),
                    "SIGNAL_WAIT_REQUIRED", "완료된 신호 대기 위치에서만 신호를 관측할 수 있습니다.")
            require(run["signal_gate"].get("accepted") is not True, "SIGNAL_ALREADY_ACCEPTED", "이 시험의 신호는 이미 통과했습니다.")
            self.data["state"] = "OBSERVING"
            self._event("signal_observation_requested", value)
            self._revision()
            self.thread = threading.Thread(target=self._signal_worker, args=(run["route"], run["step_id"]),
                name="commissioning-signal", daemon=False)
            self.thread.start()
            return {"accepted": True}
        return self._request("signal", value, action)

    def _signal_worker(self, route, step_id):
        try:
            result = self.adapter.observe_signal(route, step_id)
            with self.lock:
                self.data["run"].update(result)
                self.data.update(state="REVIEW_REQUIRED", error=None)
                self._event("signal_observed", result)
                self._revision()
        except Exception as error:
            with self.lock:
                self.data.update(state="REVIEW_REQUIRED", error=getattr(error, "code", "SIGNAL_OBSERVATION_FAILED"))
                self._event("signal_observation_failed", {"code": self.data["error"], "motion_dispatched": False})
                self._revision()

    def export(self):
        with self.lock:
            return {"schema": "pushpilot.commissioning-export.v1", "exported_at": time.time(),
                "repeatability_qualified": False, "production_applied": False,
                "routes": self.routes()["routes"],
                "drafts": [json.loads(r[0]) for r in self.db.execute("SELECT value FROM drafts ORDER BY rowid")],
                "state": deepcopy(self.data),
                "events": [{**dict(r), "value": json.loads(r["value"])} for r in self.db.execute("SELECT * FROM events ORDER BY id")]}

    def stop(self, value):
        # Set the latch before taking the service lock; a slow operation cannot
        # prevent cancellation reaching the final dispatch boundary.
        try:
            require(str(UUID(value.get("request_id"))) == value.get("request_id"),
                    "REQUEST_ID_REQUIRED", "새 UUID 요청 식별자가 필요합니다.")
        except (ValueError, TypeError, AttributeError):
            raise ConsoleError("REQUEST_ID_REQUIRED", "새 UUID 요청 식별자가 필요합니다.", 422) from None
        require(self.owner_lock is not None, "NOT_CONSOLE_OWNER", "현재 로봇은 제품 executor가 제어하고 있습니다.")
        digest = hashlib.sha256(encoded({"kind": "stop", "value": value})).hexdigest()
        with self.stop_request_lock:
            prior = self.request_cache.get(value["request_id"])
            if prior:
                require(prior[0] == digest, "REQUEST_ID_REUSED", "같은 ID로 다른 요청을 보낼 수 없습니다.")
                return deepcopy(prior[1])
            pending = self.pending_stops.get(value["request_id"])
            if pending:
                require(pending == digest, "REQUEST_ID_REUSED", "같은 ID로 다른 요청을 보낼 수 없습니다.")
                return {"accepted": True, "pending": True, "request_id": value["request_id"]}
            self.pending_stops[value["request_id"]] = digest
        self.stop_event.set()
        self.adapter.request_stop()
        def action():
            self._owned()
            self.adapter.stop("Commissioning operator requested inhibition of further motion.")
            self._event("stop_requested", {"reason": value.get("reason", "Operator Stop"), "immediate_physical_stop_claimed": False})
            if self.data["state"] != "RECONCILIATION_REQUIRED" and (not self.thread or not self.thread.is_alive()):
                self.data["state"] = "REVIEW_REQUIRED" if self.data["run"] else "READY"
            self._revision()
            return {"accepted": True, "message": "추가 이동 중단 요청. 현재 명령 결과를 확인합니다."}
        return self._request("stop", value, action)

    def camera(self):
        return self.adapter.camera()

    def artifact(self, artifact_id):
        # Adapter resolves only opaque IDs from its own session registry.
        return self.adapter.artifact(artifact_id)

    def close(self):
        if self.owner_lock:
            self.stop_event.set()
            self.adapter.request_stop()
            self.adapter.stop("Commissioning process shutting down; no automatic continuation.")
            if self.thread:
                self.thread.join()  # Keep ownership until the execution owner exits.
            self.adapter.close()
            self.owner_lock.close()
            self.owner_lock = None
            # Product reservation intentionally remains, requiring explicit
            # reconciliation after a shutdown while controlling the robot.
        self.db.close()
        self.process_owner.close()
