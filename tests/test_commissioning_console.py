"""No equipment: independent workbench orchestration and HTTP boundary checks."""
import asyncio
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from uuid import uuid4

import httpx

from backend.commissioning_console.api import create_app
from backend.commissioning_console.service import ConsoleError, ConsoleService
from backend.robot_control.service import ProcessLock
from backend.robot_control.taught_executor import ExecutionBlocked


class FakeAdapter:
    """No network, token, runtime loader, camera or robot access."""
    def __init__(self, root):
        self.production_journal_root = Path(root) / "production"
        self.calls = []
        self.reservation_requests = []
        self.reserve_error = self.execute_error = self.observe_error = self.release_error = None
        self.execute_hook = None
        self.stop_latch = threading.Event()
        self.result = {"review": {"verdict": "PASS", "summary": "Synthetic visible progress"},
                       "before_artifact_id": "before-opaque", "after_artifact_id": "after-opaque"}

    def routes(self):
        return {"routes": [{"code": "D", "destination": "HANOK", "steps": [
            {"id": "D-step-17", "primitive_id": "synthetic-push", "stages": [],
             "expected_visual": "Synthetic progress only"}], "empty_return": []}]}

    def passive_status(self):
        return {"physical": {"state": "COMPLETE"}, "robot": {"receiver": {
            "connected": True, "idle": True, "actual_pose": [0., 0., 8., 0., 0., 0.],
            "session_id": "synthetic-session", "seq": 1}}}

    def reserve(self, owner, reason, *, request_id=None):
        self.calls.append(("reserve", owner))
        self.reservation_requests.append((owner, request_id))
        if self.reserve_error:
            raise self.reserve_error

    def acquire(self, directory):
        self.calls.append(("acquire", str(directory)))

    def release_reservation(self, owner, reason):
        self.calls.append(("release_reservation", owner))

    def ready_to_release(self):
        self.calls.append(("ready_to_release", None))
        if self.release_error:
            raise self.release_error

    def close(self):
        self.calls.append(("close", None))

    def execute(self, route, step, draft, command_id):
        self.calls.append(("execute", command_id))
        if self.execute_hook:
            self.execute_hook()
        if self.execute_error:
            raise self.execute_error
        return {"command_id": command_id, "native_verified": True, "outcome": "COMPLETED"}

    def observe(self):
        self.calls.append(("observe", None))
        if self.observe_error:
            raise self.observe_error
        return deepcopy(self.result)

    def observe_signal(self, route, step):
        self.calls.append(("observe_signal", step))
        return {"signal_gate": {"accepted": False, "color": "RED"}}

    def confirm_stationary(self):
        self.calls.append(("confirm_stationary", None))

    def request_stop(self):
        self.calls.append(("request_stop", None))
        self.stop_latch.set()

    def stop(self, reason):
        self.calls.append(("stop", reason))

    def camera(self):
        return {"jpeg": b"\xff\xd8synthetic\xff\xd9", "metadata": {"id": "camera-one", "sha256": "a" * 64}}

    def artifact(self, artifact_id):
        self.calls.append(("artifact", artifact_id))
        if artifact_id not in {"before-opaque", "after-opaque"}:
            raise ConsoleError("ARTIFACT_NOT_FOUND", "Unknown opaque artifact", 404)
        return b"\xff\xd8synthetic\xff\xd9"


def request(service, **changes):
    return {"request_id": str(uuid4()), "expected_revision": service.data["revision"], **changes}


class ConsoleTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.adapter = FakeAdapter(self.root)
        self.service = ConsoleService("unused-no-file-read", self.root / "console", adapter=self.adapter)
        self.addCleanup(lambda: self.service.close())

    def acquire(self):
        return self.service.acquire(request(self.service))

    def execute(self):
        value = request(self.service, route="D", step_id="D-step-17")
        result = self.service.execute(value)
        self.join()
        return value, result

    def join(self):
        self.service.thread.join(2.)
        self.assertFalse(self.service.thread.is_alive(), "Synthetic worker did not exit")

    def test_running_c_broker_rejection_has_no_robot_io_or_local_state_change(self):
        self.adapter.reserve_error = ConsoleError("COMMISSIONING_PRODUCTION_BUSY", "Existing C is active")
        before = deepcopy(self.service.data)
        with self.assertRaises(ConsoleError) as raised:
            self.acquire()
        self.assertEqual("COMMISSIONING_PRODUCTION_BUSY", raised.exception.code)
        self.assertEqual(before, self.service.data)
        self.assertEqual(["reserve"], [k for k, _ in self.adapter.calls])
        with self.assertRaises(ConsoleError):
            self.service.stop({"request_id": str(uuid4())})
        self.assertFalse(self.adapter.stop_latch.is_set())

    def test_os_lock_conflict_never_force_unlocks_or_touches_robot(self):
        external = ProcessLock(self.adapter.production_journal_root / "runner.owner.lock")
        external.acquire()
        self.addCleanup(external.close)
        with self.assertRaises(ConsoleError) as raised:
            self.acquire()
        self.assertEqual("EXECUTOR_OWNERSHIP_CONFLICT", raised.exception.code)
        self.assertEqual("RECONCILIATION_REQUIRED", self.service.data["state"])
        self.assertIsNone(self.service.owner_lock)
        self.assertEqual(["reserve"], [k for k, _ in self.adapter.calls])
        contender = ProcessLock(external.path)
        with self.assertRaises(Exception):
            contender.acquire()

    def test_broker_timeout_preserves_exact_owner_and_request_across_restart(self):
        value = request(self.service)
        self.adapter.reserve_error = TimeoutError("Broker may already have reserved ownership")
        with self.assertRaises(TimeoutError):
            self.service.acquire(value)
        owner, broker_request = self.adapter.reservation_requests[-1]
        self.assertEqual(value["request_id"], broker_request)
        self.assertEqual(owner, self.service.data["owner_id"])
        self.assertEqual(broker_request, self.service.data["broker_request_id"])
        self.assertEqual("RECONCILIATION_REQUIRED", self.service.data["state"])
        self.assertIsNone(self.service.owner_lock)
        self.assertEqual(["reserve"], [k for k, _ in self.adapter.calls])
        self.service.close()
        adapter = FakeAdapter(self.root)
        self.service = ConsoleService("unused", self.root / "console", adapter=adapter)
        self.assertEqual(owner, self.service.data["owner_id"])
        self.assertEqual(broker_request, self.service.data["broker_request_id"])
        self.assertEqual("RECONCILIATION_REQUIRED", self.service.data["state"])
        self.assertEqual([], adapter.calls)

    def test_crash_after_durable_reservation_intent_never_reissues_post(self):
        identifier, owner = str(uuid4()), "console-before-network-crash"
        self.service.db.execute("INSERT INTO reservations VALUES(?,?,'PENDING')", (identifier, owner))
        self.service.db.commit()
        self.service.close()
        adapter = FakeAdapter(self.root)
        self.service = ConsoleService("unused", self.root / "console", adapter=adapter)
        self.assertEqual("RECONCILIATION_REQUIRED", self.service.data["state"])
        self.assertEqual(owner, self.service.data["owner_id"])
        self.assertEqual(identifier, self.service.data["broker_request_id"])
        self.assertEqual([], adapter.calls)

    def test_duplicate_execute_returns_original_acceptance_without_replay(self):
        self.acquire()
        value, response = self.execute()
        self.assertEqual(response, self.service.execute(value))
        self.assertEqual(1, sum(k == "execute" for k, _ in self.adapter.calls))
        with self.assertRaises(ConsoleError) as raised:
            self.service.execute({**value, "step_id": "changed-step"})
        self.assertEqual("REQUEST_ID_REUSED", raised.exception.code)

    def test_muse_fail_keeps_native_complete_and_requires_explicit_ack(self):
        self.acquire()
        self.adapter.result["review"]["verdict"] = "FAIL"
        self.execute()
        self.assertEqual("REVIEW_REQUIRED", self.service.data["state"])
        self.assertTrue(self.service.data["run"]["receipt"]["native_verified"])
        self.assertEqual("FAIL", self.service.data["run"]["review"]["verdict"])
        with self.assertRaises(ConsoleError):
            self.service.execute(request(self.service, route="D", step_id="D-step-17"))
        self.service.acknowledge(request(self.service, reason="Visible state reviewed for another controlled test"))
        self.assertEqual("READY", self.service.data["state"])
        self.assertEqual("FAIL", self.service.data["run"]["review"]["verdict"])
        self.assertEqual(1, sum(k == "execute" for k, _ in self.adapter.calls))

    def test_review_service_failure_can_reobserve_without_motion_replay(self):
        self.acquire()
        self.adapter.observe_error = RuntimeError("Private provider path or token must never leak")
        self.execute()
        self.assertEqual("REVIEW_REQUIRED", self.service.data["state"])
        self.assertTrue(self.service.data["run"]["receipt"]["native_verified"])
        self.adapter.observe_error = None
        self.service.observe(request(self.service))
        self.join()
        self.assertEqual("PASS", self.service.data["run"]["review"]["verdict"])
        self.assertEqual(1, sum(k == "execute" for k, _ in self.adapter.calls))

    def test_unknown_motion_blocks_ack_next_observe_release_even_after_stop(self):
        self.acquire()
        self.adapter.execute_error = TimeoutError("Exact motion UUID has unresolved outcome")
        self.execute()
        self.assertEqual("RECONCILIATION_REQUIRED", self.service.data["state"])
        self.service.stop({"request_id": str(uuid4())})
        self.assertEqual("RECONCILIATION_REQUIRED", self.service.data["state"])
        for method, changes in ((self.service.acknowledge, {"reason": "Stationary alone cannot prove original command"}),
                                (self.service.execute, {"route": "D", "step_id": "D-step-17"}),
                                (self.service.observe, {}), (self.service.release, {})):
            with self.assertRaises(ConsoleError):
                method(request(self.service, **changes))
        self.assertEqual(0, sum(k == "confirm_stationary" for k, _ in self.adapter.calls))
        self.assertEqual(0, sum(k == "release_reservation" for k, _ in self.adapter.calls))

    def test_rejected_unsent_selection_preserves_previous_signal_wait_for_reobservation(self):
        self.acquire()
        self.adapter.result["signal_gate"] = {"accepted": True, "id": "synthetic-gate"}
        self.execute()
        previous = deepcopy(self.service.data["run"])
        self.service.acknowledge(request(self.service, reason="Fresh green received at the completed wait pose"))
        rejected = ExecutionBlocked("CONSOLE_SIGNAL_GREEN_REQUIRED", "The previously observed green has expired")
        rejected.known_before_execute = True
        self.adapter.execute_error = rejected
        self.execute()
        status = self.service.data
        self.assertEqual("REVIEW_REQUIRED", status["state"])
        self.assertEqual(previous["receipt"], status["run"]["receipt"])
        self.assertEqual(previous["command_id"], status["run"]["command_id"])
        self.assertFalse(status["run"]["signal_gate"]["accepted"])
        self.assertEqual("REJECTED_UNSENT", status["last_operation"]["state"])
        with self.assertRaises(ConsoleError) as raised:
            self.service.acknowledge(request(self.service, reason="Cannot reuse the expired green admission"))
        self.assertEqual("SIGNAL_GREEN_REQUIRED", raised.exception.code)
        self.service.signal(request(self.service))
        self.join()
        self.assertEqual("RED", self.service.data["run"]["signal_gate"]["color"])

    def test_rejected_first_selection_remains_ready_without_fake_receipt(self):
        self.acquire()
        rejected = ExecutionBlocked("CONSOLE_EXACT_SOURCE", "Wrong source; nothing was dispatched")
        rejected.known_before_execute = True
        self.adapter.execute_error = rejected
        self.execute()
        self.assertEqual("READY", self.service.data["state"])
        self.assertIsNone(self.service.data["run"])
        self.assertEqual("REJECTED_UNSENT", self.service.data["last_operation"]["state"])

    def test_stop_latch_reaches_blocked_worker_before_service_lock(self):
        self.acquire()
        entered = threading.Event()
        def blocked():
            entered.set()
            if not self.adapter.stop_latch.wait(2.):
                raise AssertionError("Stop never reached blocked adapter")
            raise ExecutionBlocked("MISSION_STOPPED", "Synthetic pre-dispatch stop")
        self.adapter.execute_hook = blocked
        self.service.execute(request(self.service, route="D", step_id="D-step-17"))
        self.assertTrue(entered.wait(1.))
        errors = []
        with self.service.lock:
            def stop():
                try:
                    self.service.stop({"request_id": str(uuid4())})
                except Exception as error:
                    errors.append(error)
            thread = threading.Thread(target=stop)
            thread.start()
            self.assertTrue(self.adapter.stop_latch.wait(1.), "Stop was blocked behind service lock")
        thread.join(2.)
        self.join()
        self.assertEqual([], errors)
        self.assertEqual("RECONCILIATION_REQUIRED", self.service.data["state"])

    def test_invalid_stop_identity_does_not_signal_the_adapter(self):
        self.acquire()
        with self.assertRaises(ConsoleError):
            self.service.stop({"request_id": "x" * 36})
        self.assertFalse(self.adapter.stop_latch.is_set())

    def test_delayed_duplicate_stop_does_not_cancel_a_later_trial(self):
        self.acquire()
        self.execute()
        stop = {"request_id": str(uuid4()), "reason": "First trial Stop"}
        original = self.service.stop(stop)
        self.service.acknowledge(request(self.service, reason="Original completed trial inspected at rest"))
        self.adapter.stop_latch.clear()
        calls = sum(k == "request_stop" for k, _ in self.adapter.calls)
        self.assertEqual(original, self.service.stop(stop))
        self.assertEqual(calls, sum(k == "request_stop" for k, _ in self.adapter.calls))
        self.assertFalse(self.adapter.stop_latch.is_set())

    def test_restart_preserves_history_and_never_auto_executes(self):
        self.acquire()
        self.execute()
        self.service.close()
        adapter = FakeAdapter(self.root)
        self.service = ConsoleService("unused", self.root / "console", adapter=adapter)
        self.assertEqual("RECONCILIATION_REQUIRED", self.service.data["state"])
        self.assertEqual("CONSOLE_RESTART_RECONCILIATION_REQUIRED", self.service.data["error"])
        self.assertEqual([], adapter.calls)
        self.assertIsNone(self.service.thread)
        self.assertTrue(self.service.data["run"]["receipt"]["native_verified"])

    def test_readonly_close_never_stops_product_or_calls_adapter_close(self):
        self.service.close()
        self.assertEqual([], self.adapter.calls)
        self.service = ConsoleService("unused", self.root / "console", adapter=self.adapter)


class ConsoleBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = TemporaryDirectory()
        self.adapter = FakeAdapter(self.temp.name)
        self.service = ConsoleService("unused", Path(self.temp.name) / "console", adapter=self.adapter)
        self.secret = "private-console-token-32-bytes-no-robot-token"
        self.app = create_app(self.service, self.secret, allowed_hosts=["console.test:8192"], manage_lifecycle=False)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://console.test:8192")
        self.origin = {"Origin": "http://console.test:8192"}

    async def asyncTearDown(self):
        await self.client.aclose()
        self.service.close()
        self.temp.cleanup()

    async def login(self):
        response = await self.client.post("/api/login", json={"token": self.secret}, headers=self.origin)
        self.assertEqual(200, response.status_code)
        self.assertIn("HttpOnly", response.headers["set-cookie"])
        self.assertIn("SameSite=strict", response.headers["set-cookie"])
        return response

    async def test_authentication_host_origin_and_token_non_disclosure(self):
        unauthenticated = await self.client.get("/api/status")
        self.assertEqual(401, unauthenticated.status_code)
        host = await self.client.get("/health", headers={"Host": "evil.test:8192"})
        self.assertEqual(403, host.status_code)
        origin = await self.client.post("/api/login", json={"token": self.secret}, headers={"Origin": "http://evil.test"})
        self.assertEqual(403, origin.status_code)
        login = await self.login()
        for url in ("/api/status", "/api/routes", "/api/export", "/static/app.js", "/health"):
            response = await self.client.get(url)
            self.assertEqual(200, response.status_code)
            self.assertNotIn(self.secret, response.text)
            self.assertEqual("no-store", response.headers["cache-control"])
        self.assertNotIn(self.secret, login.text)
        self.assertEqual([], self.adapter.calls)

    async def test_bounded_json_unknown_fields_and_private_error_redaction(self):
        await self.login()
        oversized = await self.client.post("/api/execute", content=b" " * 65537,
            headers={**self.origin, "Content-Type": "application/json"})
        self.assertEqual(413, oversized.status_code)
        non_json = await self.client.post("/api/execute", content="not json", headers=self.origin)
        self.assertEqual(415, non_json.status_code)
        extra = await self.client.post("/api/session/acquire", json=request(self.service, arbitrary_url="http://robot"), headers=self.origin)
        self.assertEqual(422, extra.status_code)
        self.adapter.reserve_error = RuntimeError("password TOKEN secret /private/config.env")
        failure = await self.client.post("/api/session/acquire", json=request(self.service), headers=self.origin)
        self.assertEqual(503, failure.status_code)
        for secret in ("password", "TOKEN", "config.env", "secret"):
            self.assertNotIn(secret, failure.text)

    async def test_artifact_requests_require_auth_and_reject_traversal(self):
        denied = await self.client.get("/api/artifacts/before-opaque")
        self.assertEqual(401, denied.status_code)
        await self.login()
        image = await self.client.get("/api/artifacts/before-opaque")
        self.assertEqual(200, image.status_code)
        for path in ("/api/artifacts/..%2f..%2fcontrol.token", "/api/artifacts/%2e%2e%5ccontrol.token",
                     "/api/artifacts/unknown-id"):
            response = await self.client.get(path)
            self.assertIn(response.status_code, {404, 422})
            self.assertNotIn(self.secret, response.text)
