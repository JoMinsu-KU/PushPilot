"""Virtual-delay profile/driver integration: no robot or network access."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from backend.robot_control.mission_profile import ReviewedProfilePreparer
from backend.robot_control.taught_executor import ExecutionBlocked
from backend.robot_control.taught_ports import PrivateJournal
from tests.test_mission_profile import FakeGuardedAPI, SOURCE, JOINTS
from tests import test_mission_driver as driver_fixtures


class DelayedStatusAPI(FakeGuardedAPI):
    def __init__(self):
        super().__init__()
        self.remaining = 0
        self.status.update(mode='physical_commissioning', hardware_connected=True)
        self.status['receiver'].update(stage='idle', reason='RECEIVER_IDLE',
            native_telemetry_available=True, native_telemetry=None, state_age_s=.1)

    def __call__(self, path, payload=None):
        result = super().__call__(path,payload)
        if path=='/v1/status' and self.remaining:
            self.remaining-=1
            result['receiver'].update(idle=False,stage='native_wait',reason='RECEIVER_NATIVE_WAIT',
                native_telemetry_available=False,
                native_telemetry={'reason':'NATIVE_TELEMETRY_UNAVAILABLE','phase':'stationary'})
        return result


class MissionStatusWaitTests(unittest.TestCase):
    def setUp(self):
        self.temporary=TemporaryDirectory()
        self.journal=PrivateJournal(self.temporary.name)
        self.api=DelayedStatusAPI()
        self.time=0.
        self.stop=False
        self.on_sleep=None

    def tearDown(self):
        self.journal.close();self.temporary.cleanup()

    def sleep(self,seconds):
        self.time+=30.  # Deliberately exceed a two-minute budget with six polls.
        if self.on_sleep:self.on_sleep()

    def stop_check(self):
        if self.stop:raise ExecutionBlocked('MISSION_STOPPED','Synthetic Stop during Native wait')

    def preparer(self):
        return ReviewedProfilePreparer(api=self.api,journal=self.journal,native_snapshot=self.api.native,
            receiver_policy=SimpleNamespace(),stop_check=self.stop_check,
            status_wait_timeout_s=None,monotonic=lambda:self.time,sleep=self.sleep)

    def test_explicit_execution_wait_survives_long_delay_without_any_command(self):
        self.api.remaining=6
        actual=self.preparer()._idle()
        self.assertTrue(actual['receiver']['idle'])
        self.assertGreater(self.time,120.)
        self.assertTrue(all(path=='/v1/status' for path,_ in self.api.calls))
        self.assertEqual(self.api.status['receiver']['seq'],1)

    def test_completed_query_waits_for_recovery_without_resubmitting(self):
        self.api.remaining=2
        self.api.after_call=lambda command:setattr(self.api,'remaining',3)
        expected={key:self.api.status['receiver'][key] for key in ('session_id','seq','profile_id')}
        _,actual=self.preparer()._query('inspect_current',self.api.status['installation']['installation_id'],
            expected,SOURCE,JOINTS)
        self.assertEqual(actual['receiver']['seq'],2)
        self.assertEqual(len([1 for path,_ in self.api.calls if path=='/v1/commands']),1)
        self.assertFalse(any(path=='/v1/arm' for path,_ in self.api.calls))

    def test_stop_cancels_unbounded_wait_before_dispatch(self):
        self.api.remaining=100
        self.on_sleep=lambda:setattr(self,'stop',True)
        with self.assertRaises(ExecutionBlocked) as error:self.preparer()._idle()
        self.assertEqual(error.exception.code,'MISSION_STOPPED')
        self.assertFalse(any(payload is not None for _,payload in self.api.calls))

    def test_readiness_uses_nonwaiting_status_and_stop_cancels_prepare_generation(self):
        factory=driver_fixtures.DriverTests()
        with TemporaryDirectory() as root:
            driver,_=factory.make_driver(Path(root))
            driver.readiness()
            calls=[]
            original=driver.ports._status
            driver.ports.status_nowait=lambda:(calls.append('nowait'),original())[1]
            driver.ports._status=lambda:(_ for _ in ()).throw(AssertionError('readiness blocked on execution wait'))
            self.assertTrue(driver.readiness()['ready'])
            self.assertEqual(calls,['nowait'])
            driver._prepare_wait_generation=driver._stop_generation
            driver._status_wait_not_stopped()  # The old initial Stop is not a new concurrent Stop.
            driver.hold('Synthetic concurrent Stop')
            with self.assertRaises(ExecutionBlocked) as error:driver._status_wait_not_stopped()
            self.assertEqual(error.exception.code,'MISSION_STOPPED')
            driver._prepare_wait_generation=None
            driver.close()


if __name__=='__main__':unittest.main()
