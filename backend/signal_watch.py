"""Deliberate bounded stopped-signal watching, never physical robot control."""
from __future__ import annotations

import asyncio
from copy import deepcopy
import math
import time
from uuid import UUID, uuid4, uuid5

from backend.core import CommandError
from backend.scene import SceneError


class SignalWatchService:
    def __init__(self, store, intelligence, *, clock=time.monotonic, sleep=asyncio.sleep):
        self.store, self.intelligence = store, intelligence
        self._clock, self._sleep = clock, sleep
        self._tasks: dict[str, asyncio.Task] = {}
        self._closed = False
        with store._lock, store._db:
            state = store._load()
            watch = state.get("signal_watch")
            if watch and watch.get("status") == "running":
                self._terminal(state, "interrupted", "The application restarted. Signal watching was not resumed.")

    def _terminal(self, state, status, detail):
        watch = state["signal_watch"]
        watch.update(status=status, detail=detail)
        state["revision"] += 1
        self.store._event(state, "SIGNAL_WATCH_FINISHED", "Signal watch: " + status, detail, "system")
        self.store._save(state)

    def _finish_watch(self, identifier, status, detail):
        with self.store._lock, self.store._db:
            state = self.store._load()
            watch = state.get("signal_watch")
            if watch and watch["id"] == identifier and watch["status"] == "running":
                self._terminal(state, status, detail)

    @staticmethod
    def _settings(payload):
        attempts = payload.get("max_attempts", 30)
        interval = payload.get("interval_seconds", 2.0)
        duration = payload.get("max_duration_seconds", 300.0)
        if (type(attempts) is not int or not 1 <= attempts <= 60
                or any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
                       for value in (interval, duration))
                or not 0.5 <= interval <= 10 or not 1 <= duration <= 900):
            raise CommandError("Use 1 to 60 attempts, 0.5 to 10 seconds between observations and a 1 to 900 second watch budget.", 422)
        return attempts, interval, duration

    async def start(self, payload):
        kind = "live-signal-watch"
        attempts, interval, duration = self._settings(payload)
        if self._closed:
            raise CommandError("Signal watching is closed. Restart the application before starting a new watch.")
        with self.store._lock, self.store._db:
            prior = self.intelligence._prior(kind, payload)
            if prior:
                return prior
            state = self.store._load()
            self.intelligence._check_revision(state, payload)
            if (state.get("signal_watch") or {}).get("status") == "running":
                raise CommandError("A signal watch is already running. Stop it before starting another.")
            binding = self.intelligence._stop_binding(state)
            # This checks the current registered view only; no frame is persisted
            # or sent to MUSE until the deliberate worker observation below.
            self.intelligence.camera.capture()
            watch_id = str(uuid4())
            deadline = self._clock() + duration
            state["signal_watch"] = {
                "id": watch_id, "status": "running", "attempts": 0, "max_attempts": attempts,
                "interval_seconds": interval, "max_duration_seconds": duration,
                "started_at": self.store._at(),
                "detail": "Watching this stopped simulation context with a finite request budget. No physical robot is controlled.",
            }
            state["revision"] += 1
            self.store._event(state, "SIGNAL_WATCH_STARTED", "Signal watch started", state["signal_watch"]["detail"], "operator")
            self.store._save(state)
            self.intelligence._reserve(kind, payload, {**binding, "watch": deepcopy(state["signal_watch"])})
            response = self.intelligence._finish(payload["request_id"], self.store._snapshot(state), 200)
        task = asyncio.create_task(self._watch(watch_id, binding, attempts, interval, deadline))
        self._tasks[watch_id] = task
        task.add_done_callback(lambda _task: self._tasks.pop(watch_id, None))
        return response

    @staticmethod
    def _same_plan_stop(state, binding):
        plan = state.get("plan") or {}
        receipt = state.get("stop_receipt") or {}
        return (state["session_id"] == binding["session_id"] and plan.get("id") == binding["plan_id"]
                and plan.get("revision") == binding["plan_revision"]
                and receipt.get("id") == binding["stop_receipt"]["id"])

    async def _watch(self, identifier, binding, attempts, interval, deadline):
        try:
            for index in range(attempts):
                if self._clock() >= deadline:
                    self._finish_watch(identifier, "exhausted", "The finite signal-watch time budget ended. The simulation remains stopped unless separately admitted.")
                    return
                with self.store._lock, self.store._db:
                    state = self.store._load()
                    watch = state.get("signal_watch")
                    if not watch or watch["id"] != identifier or watch["status"] != "running":
                        return
                    if not self._same_plan_stop(state, binding) or not state["approved"] or state["state"] == "CANCELLED":
                        self._terminal(state, "cancelled", "The mission, plan or stop context changed. No further observation will be sent.")
                        return
                    if state["state"] != "WAITING_SIGNAL":
                        admitted = state["state"] == "REVIEW_REQUIRED" and self.store._kind(state) == "CROSS"
                        self._terminal(state, "green_admitted" if admitted else "cancelled",
                                       "The current simulated crossing was admitted; its action review is still required." if admitted else
                                       "The stopped observation context is no longer active. No further observation will be sent.")
                        return
                    if self.intelligence._stop_binding(state) != binding:
                        self._terminal(state, "cancelled", "The stopped junction or map binding changed. No further observation will be sent.")
                        return
                    watch["attempts"] = index + 1
                    watch["detail"] = "Awaiting a new native-frame MUSE judgment for this stopped simulation context."
                    state["revision"] += 1
                    self.store._save(state)
                    child = {"request_id": str(uuid5(UUID(identifier), f"attempt-{index + 1}")), "expected_revision": state["revision"]}
                # No SQLite/store lock is held while capture or inference awaits.
                remaining = deadline - self._clock()
                if remaining <= 0:
                    raise TimeoutError
                response, status = await asyncio.wait_for(self.intelligence.review_signal(child), remaining)
                if status != 200:
                    self._finish_watch(identifier, "held", "Signal review failed or its context changed. No fallback color was used; inspect the current stopped state.")
                    return
                with self.store._lock, self.store._db:
                    state = self.store._load()
                    watch = state.get("signal_watch")
                    if not watch or watch["id"] != identifier or watch["status"] != "running":
                        return
                    if not self._same_plan_stop(state, binding) or not state["approved"]:
                        self._terminal(state, "cancelled", "The mission or stop context changed. No further observation will be sent.")
                        return
                    if state["state"] == "REVIEW_REQUIRED" and self.store._kind(state) == "CROSS":
                        self._terminal(state, "green_admitted", "A current MUSE GREEN admitted this simulated crossing. Its action review is still required; no next action was run.")
                        return
                    if state["state"] != "WAITING_SIGNAL" or response["state"] != "WAITING_SIGNAL":
                        self._terminal(state, "cancelled", "The stopped observation context changed. No further observation will be sent.")
                        return
                if index + 1 < attempts:
                    remaining = deadline - self._clock()
                    if remaining <= 0:
                        raise TimeoutError
                    await self._sleep(min(interval, remaining))
            self._finish_watch(identifier, "exhausted", "The finite signal-watch attempt budget ended. RED or UNKNOWN did not admit a crossing; request another watch explicitly if appropriate.")
        except TimeoutError:
            self._finish_watch(identifier, "exhausted", "The finite signal-watch time budget ended. No further judgment will be sent automatically.")
        except asyncio.CancelledError:
            self._finish_watch(identifier, "interrupted", "Signal watching was interrupted. No observation or action is replayed.")
            raise
        except (CommandError, SceneError):
            self._finish_watch(identifier, "held", "The stop, map, camera or provider context became unavailable. No further judgment will be sent automatically.")
        except Exception:
            self._finish_watch(identifier, "held", "Signal watching failed. Inspect current evidence; no fallback color or physical stop was assumed.")

    async def stop(self, payload):
        kind = "live-signal-watch-stop"
        with self.store._lock, self.store._db:
            prior = self.intelligence._prior(kind, payload)
            if prior:
                return prior
            state = self.store._load()
            self.intelligence._check_revision(state, payload)
            watch = state.get("signal_watch")
            if not watch or watch["status"] != "running":
                raise CommandError("There is no running signal watch to stop.")
            identifier = watch["id"]
            self._terminal(state, "cancelled", "The operator stopped this signal watch. This does not stop or control a physical robot.")
            self.intelligence._reserve(kind, payload, {"watch_id": identifier})
            response = self.intelligence._finish(payload["request_id"], self.store._snapshot(state), 200)
        task = self._tasks.get(identifier)
        if task and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        return response

    async def close(self):
        self._closed = True
        with self.store._lock, self.store._db:
            state = self.store._load()
            if (state.get("signal_watch") or {}).get("status") == "running":
                self._terminal(state, "interrupted", "The application closed. Signal watching will not resume after restart.")
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
