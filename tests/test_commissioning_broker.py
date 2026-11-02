"""Equipment-free ownership handoff tests; no robot, provider or live runtime."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.responses import JSONResponse
import httpx

from backend.core import CommandError
from backend.physical_mission import PhysicalMissionService
from backend.physical_api import router
from backend.robot_control.service import ProcessLock
from backend.robot_control.site_trial_driver import SiteTrialMissionDriver
from backend.robot_control.taught_executor import ExecutionBlocked
from tests.test_physical_mission import FakeWorkspace, FakeMeasuredDriver, command_for
from tests.test_site_trial_driver import fixture, SitePorts, Observer


def request(service, **changes):
    return {"request_id": str(uuid4()), "expected_revision": service.snapshot()["revision"],
            "owner_id": "offline-test-owner", "reason": "Explicit synthetic ownership test", **changes}


class BrokerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = TemporaryDirectory()
        self.driver, self.store = FakeMeasuredDriver(), FakeWorkspace()
        self.calls = []
        def handoff(owner, reason):
            self.calls.append(("handoff", owner))
            return {"motion_issued": False, "ownership_released": True}
        def rejoin(owner, reason):
            self.calls.append(("rejoin", owner))
            return {"motion_issued": False, "at_start": True, "stationary": True}
        self.driver.commissioning_handoff = handoff
        self.driver.commissioning_rejoin = rejoin
        self.service = PhysicalMissionService(self.store, self.temp.name, driver=self.driver)

    async def asyncTearDown(self):
        await self.service.close()
        self.temp.cleanup()

    async def test_active_and_held_missions_reject_without_driver_or_state_mutation(self):
        for state in ("MOVING", "WAITING_SIGNAL", "OBSERVING", "HOLD", "STARTING"):
            self.service.status.update(state=state, mission_id="existing-c")
            before = self.service.snapshot()
            with self.assertRaises(CommandError):
                await self.service.commissioning_acquire(request(self.service))
            self.assertEqual(before, self.service.snapshot())
            self.assertEqual([], self.calls)
            self.assertEqual([], self.driver.holds)
            self.assertEqual([], self.driver.commands)

    async def test_reservation_blocks_production_commands_and_readiness(self):
        acquired = await self.service.commissioning_acquire(request(self.service))
        self.assertTrue(acquired["commissioning"]["reserved"])
        self.driver.readiness = lambda: self.fail("Reserved monitor must not reacquire production journal")
        await self.service.refresh_readiness()
        self.assertFalse(self.service.snapshot()["available"])
        production = command_for(self.service, self.store)
        for method in (self.service.start, self.service.stop, self.service.reset,
                       self.service.resume, self.service.prepare_boundary):
            with self.assertRaisesRegex(CommandError, "COMMISSIONING_RESERVED"):
                await method(production)
        self.assertEqual([], self.driver.holds)
        self.assertEqual([], self.driver.commands)

    async def test_exact_owner_and_revision_and_no_automatic_mission(self):
        acquire = request(self.service)
        response = await self.service.commissioning_acquire(acquire)
        self.assertEqual(response, await self.service.commissioning_acquire(acquire))
        with self.assertRaises(CommandError):
            await self.service.commissioning_release(request(self.service, owner_id="different-owner"))
        with self.assertRaises(CommandError):
            await self.service.commissioning_release(request(self.service, expected_revision=0))
        result = await self.service.commissioning_release(request(self.service))
        self.assertFalse(result["commissioning"]["reserved"])
        self.assertIsNone(self.service.task)
        self.assertEqual([], self.driver.commands)

    async def test_reservation_survives_restart_without_readiness_takeover(self):
        await self.service.commissioning_acquire(request(self.service))
        await self.service.close()
        self.service = PhysicalMissionService(self.store, self.temp.name, driver=self.driver)
        self.driver.readiness = lambda: self.fail("Restart must preserve test ownership")
        self.assertTrue(self.service.snapshot()["commissioning"]["reserved"])
        await self.service.refresh_readiness()

    async def test_rejoin_failure_keeps_reservation_and_original_complete_history(self):
        self.service.status.update(state="COMPLETE", mission_id="finished-c", error=None)
        self.service.status["progress"] = {"completed": 30, "total": 30}
        await self.service.commissioning_acquire(request(self.service))
        def fail(owner, reason):
            raise ExecutionBlocked("COMMISSIONING_COMMON_START_REQUIRED", "Synthetic tool is mid-course")
        self.driver.commissioning_rejoin = fail
        with self.assertRaisesRegex(CommandError, "COMMON_START_REQUIRED"):
            await self.service.commissioning_release(request(self.service))
        status = self.service.snapshot()
        self.assertTrue(status["commissioning"]["reserved"])
        self.assertEqual("COMPLETE", status["state"])
        self.assertEqual({"completed": 30, "total": 30}, status["progress"])

    async def test_same_origin_api_and_bounded_command_schema(self):
        app = FastAPI()
        app.state.physical = self.service
        app.include_router(router)
        @app.exception_handler(CommandError)
        async def command_error(_request, error):
            return JSONResponse({"message": str(error)}, status_code=error.status)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            rejected = await client.post("/api/v1/physical/commissioning/acquire", json=request(self.service),
                                         headers={"Origin": "http://other-site"})
            self.assertEqual(403, rejected.status_code)
            malformed = await client.post("/api/v1/physical/commissioning/acquire", json=request(self.service, arbitrary_target=[1, 2]),
                                          headers={"Origin": "http://testserver"})
            self.assertEqual(422, malformed.status_code)
            self.assertEqual([], self.calls)
            acquired = await client.post("/api/v1/physical/commissioning/acquire", json=request(self.service),
                                         headers={"Origin": "http://testserver"})
            self.assertEqual(200, acquired.status_code)
            released = await client.post("/api/v1/physical/commissioning/release", json=request(self.service),
                                         headers={"Origin": "http://testserver"})
            self.assertEqual(200, released.status_code)


class DriverOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        path, self.config, self.packet, _, _ = fixture(self.root)
        self.patch = patch("backend.robot_control.site_trial_driver.load_runtime", return_value={
            "policy": SimpleNamespace(MAX_PROFILE_BYTES=65536, valid=lambda *args: None)})
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.driver = SiteTrialMissionDriver(path, Observer(), port_factory=SitePorts)
        self.driver._ensure_ports()
        self.raw = self.driver.ports.raw
        self.raw.status.update(mode="physical_commissioning", hardware_connected=True)
        self.driver._pin(self.raw.status)
        self.driver.journal.checkpoint({"state": "STATIONARY_COMMAND_COMPLETE"})
        self.addCleanup(lambda: self.driver.journal.close() if self.driver.journal else None)

    def test_handoff_releases_exact_lock_without_hold_or_any_post(self):
        ports, journal = self.driver.ports, self.driver.journal
        lock = ProcessLock(journal.root / "runner.owner.lock")
        with self.assertRaises(Exception):
            lock.acquire()
        proof = self.driver.commissioning_handoff("offline-test-owner", "Explicit no-motion ownership test")
        self.assertTrue(proof["ownership_released"])
        self.assertEqual([], ports.holds)
        self.assertTrue(all(payload is None for _, payload in self.raw.calls))
        self.assertIsNone(self.driver.ports)
        lock.acquire()
        lock.close()

    def test_unresolved_checkpoint_does_not_release_owner(self):
        self.driver.journal.checkpoint({"state": "DISPATCH_UNRESOLVED"})
        with self.assertRaisesRegex(ExecutionBlocked, "unresolved"):
            self.driver.commissioning_handoff("offline-test-owner", "Do not bypass unknown command")
        self.assertIsNotNone(self.driver.journal)
        self.assertEqual([], self.driver.ports.holds)

    def test_armed_or_pending_receiver_never_releases_owner(self):
        original = deepcopy(self.raw.status)
        for mutate in (lambda s: s.update(armed=True), lambda s: s.update(hold=False),
                       lambda s: s.update(active_commands=[{"id": "unknown"}]),
                       lambda s: s["receiver"].update(profile_pending=True),
                       lambda s: s["receiver"].update(idle=False)):
            self.raw.status = deepcopy(original)
            mutate(self.raw.status)
            with self.assertRaises(ExecutionBlocked):
                self.driver.commissioning_handoff("offline-test-owner", "A busy receiver cannot transfer ownership")
            self.assertIsNotNone(self.driver.journal)
        self.assertEqual([], self.driver.ports.holds)

    def test_rejoin_refuses_external_os_owner_before_status_requests(self):
        self.driver.commissioning_handoff("offline-test-owner", "Explicit no-motion ownership test")
        lock = ProcessLock(Path(self.config["journal_root"]) / "runner.owner.lock")
        lock.acquire()
        self.addCleanup(lock.close)
        with self.assertRaises(Exception):
            self.driver.commissioning_rejoin("offline-test-owner", "Still owned by the test process")

    def test_rejoin_at_start_and_changed_configuration_rejected(self):
        self.driver.commissioning_handoff("offline-test-owner", "Explicit no-motion ownership test")
        original_factory = self.driver.port_factory
        def existing_state_ports(**kwargs):
            ports = original_factory(**kwargs)
            ports.raw = self.raw
            ports.api = self.raw
            return ports
        self.driver.port_factory = existing_state_ports
        proof = self.driver.commissioning_rejoin("offline-test-owner", "Return ownership at common START")
        self.assertTrue(proof["at_start"])
        self.assertFalse(proof["motion_issued"])
        self.assertIsNone(self.driver.ports)
        self.driver.config_file.write_text(self.driver.config_file.read_text() + " ")
        with self.assertRaises(ExecutionBlocked) as raised:
            self.driver.commissioning_rejoin("offline-test-owner", "Changed source cannot rejoin")
        self.assertEqual("COMMISSIONING_HANDOFF_MISMATCH", raised.exception.code)

    def test_rejoin_midcourse_refuses_and_preserves_no_mutation(self):
        self.driver.commissioning_handoff("offline-test-owner", "Explicit no-motion ownership test")
        original_factory = self.driver.port_factory
        def midcourse_ports(**kwargs):
            ports = original_factory(**kwargs)
            ports.raw = self.raw
            ports.api = self.raw
            return ports
        self.driver.port_factory = midcourse_ports
        self.raw.status["receiver"]["actual_pose"][0] += 10.
        with self.assertRaises(ExecutionBlocked) as raised:
            self.driver.commissioning_rejoin("offline-test-owner", "Midcourse tool cannot rejoin production")
        self.assertEqual("COMMISSIONING_COMMON_START_REQUIRED", raised.exception.code)
        self.assertTrue(all(payload is None for _, payload in self.raw.calls))
