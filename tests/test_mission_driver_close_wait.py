"""Shutdown drains a cancelled preparation before closing its private journal."""
from copy import deepcopy
import threading
from types import SimpleNamespace
import unittest

from backend.robot_control.mission_driver import ConfigBackedMissionDriver
from backend.robot_control.status_wait import wait_for_stationary_status
from backend.robot_control.taught_executor import ExecutionBlocked
from tests.test_mission_driver import deployment_status


class DriverCloseWaitTests(unittest.TestCase):
    def test_close_preserves_wait_cancellation_evidence_until_execution_owner_exits(self):
        for failed_hold in (False, True):
            with self.subTest(failed_hold=failed_hold):
                self.check_close(failed_hold)

    def check_close(self, failed_hold):
        driver = object.__new__(ConfigBackedMissionDriver)
        driver.execution_lock = threading.Lock()
        driver._stop_lock = threading.Lock()
        driver._stop_generation = 0
        driver._prepare_wait_generation = 0
        driver.stop_latch = threading.Event()
        driver.currentplan = None
        entered, held, cancelled, flush_allowed, journal_closed = (threading.Event() for _ in range(5))
        entries, worker_errors, close_errors = [], [], []

        def append(kind, payload):
            if journal_closed.is_set():
                raise AssertionError("Preparation wrote after journal ownership was released")
            entries.append(kind)

        driver.journal = SimpleNamespace(append=append, close=journal_closed.set)

        def hold(reason):
            held.set()
            if failed_hold:
                raise OSError("Synthetic bounded hold delivery failure")

        driver.ports = SimpleNamespace(hold=hold)
        status = deployment_status()
        status["receiver"].update(idle=False, stage="native_wait", reason="RECEIVER_NATIVE_WAIT",
            native_telemetry_available=False, state_age_s=.1,
            native_telemetry={"reason": "NATIVE_TELEMETRY_UNAVAILABLE", "phase": "stationary"})

        def get_status():
            entered.set()
            return deepcopy(status)

        def worker():
            try:
                with driver.execution_lock:
                    try:
                        wait_for_stationary_status(get_status, driver.journal,
                            driver._status_wait_not_stopped, timeout_s=None,
                            sleep=lambda _: held.wait(2.))
                    except ExecutionBlocked as error:
                        if error.code != "MISSION_STOPPED":
                            raise
                        cancelled.set()
                        if not flush_allowed.wait(2.):
                            raise AssertionError("Test did not release cancellation evidence flush")
                        driver.journal.append("preparation_cancelled", {"motion_issued": False})
            except BaseException as error:
                worker_errors.append(error)

        def closing():
            try:
                driver.close()
            except BaseException as error:
                close_errors.append(error)

        worker_thread = threading.Thread(target=worker, daemon=True)
        close_thread = threading.Thread(target=closing, daemon=True)
        worker_thread.start()
        try:
            self.assertTrue(entered.wait(2.))
            close_thread.start()
            self.assertTrue(held.wait(2.))
            self.assertTrue(cancelled.wait(2.))
            self.assertTrue(driver.stop_latch.is_set())
            self.assertFalse(journal_closed.is_set())
            self.assertTrue(close_thread.is_alive())
        finally:
            flush_allowed.set()
            worker_thread.join(2.)
            if close_thread.ident is not None:
                close_thread.join(2.)
        self.assertFalse(worker_thread.is_alive())
        self.assertFalse(close_thread.is_alive())
        self.assertEqual(worker_errors, [])
        self.assertIn("preparation_cancelled", entries)
        self.assertTrue(journal_closed.is_set())
        if failed_hold:
            self.assertEqual(len(close_errors), 1)
            self.assertIsInstance(close_errors[0], OSError)
        else:
            self.assertEqual(close_errors, [])


if __name__ == "__main__":
    unittest.main()
