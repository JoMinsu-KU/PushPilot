"""No-equipment checks for explicit review-only continuation and no replay."""
import asyncio
from copy import deepcopy
from dataclasses import asdict, replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4

from backend.core import CommandError
from backend.physical_mission import PhysicalMissionService
from backend.robot_control.mission_policy import Phase, MissionState
from backend.robot_control.mission_resume import REVIEW_HOLD, resume_candidate, state_from_dict, read_chain
from backend.robot_control.taught_executor import ExecutionBlocked
from backend.robot_control.taught_ports import PrivateJournal
from tests.test_mission_policy import plan
from tests.test_physical_mission import FakeWorkspace, FakeMeasuredDriver, command_for


def fixture():
    original = plan(signal=True)
    def trial(p):
        return replace(p, release_mode='site_trial', qualified=False, current_site_review_sha256='c'*64)
    gate=replace(original.steps[0].signal_gate, recontact=trial(original.steps[0].signal_gate.recontact),
        release_to_wait=trial(original.steps[0].signal_gate.release_to_wait), entry_policy='single_departure')
    first=replace(original.steps[0], primitive=trial(original.steps[0].primitive), signal_gate=gate)
    crossing=replace(original.steps[1], id='crossing', at_goal=False,
        primitive=replace(trial(original.steps[1].primitive), target_context_id='CROSSED'))
    primitive=replace(trial(original.steps[1].primitive), id='completed-unit', source_context_id='CROSSED', target_context_id='OBSERVE')
    intermediate=replace(original.steps[1], id='C-step-17', primitive=primitive, at_goal=False)
    final=replace(original.steps[1], id='C-step-18', primitive=replace(trial(original.steps[1].primitive),id='next',source_context_id='OBSERVE'))
    original=replace(original, destination='VILLA', release_mode='site_trial',
        parking=replace(original.parking,mode='delivery_only'), steps=(first,crossing,intermediate,final),
        empty_return=tuple(trial(p) for p in original.empty_return))
    updated=replace(original, binding=replace(original.binding,calibration_id='new-registration'),
        steps=tuple(replace(s,review_mode='intermediate_progress') if not s.at_goal else s for s in original.steps))
    state=MissionState(original.id,'session',phase=Phase.OBSERVE,step_index=2,
        action_command_id='completed',last_motion_completed_at_s=10.,start_verified=True,
        issued_command_ids=('completed',),signal_step_index=0)
    held=replace(state,phase=Phase.FAILED,reason=REVIEW_HOLD,reobservations=3)
    receipt=dict(command_id='completed',primitive_id=primitive.id,session_id='session',
        target_context_id=primitive.target_context_id,completed_at_s=10.,native_verified=True,outcome='COMPLETED')
    return original,updated,held,state,receipt


class CandidateTests(unittest.TestCase):
    def test_restores_observation_not_completed_motion(self):
        args = fixture()
        recovered, state = resume_candidate(*args)
        self.assertEqual(state.phase, Phase.OBSERVE)
        self.assertEqual(state.step_index, args[2].step_index)
        self.assertEqual(state.issued_command_ids, ('completed',))
        self.assertIsNone(state.pending_command_id)
        self.assertEqual(state.reobservations, 0)
        self.assertEqual(args[2].phase, Phase.FAILED)
        self.assertEqual(recovered.binding.calibration_id, 'new-registration')

    def test_changed_geometry_destination_binding_or_limits_rejected(self):
        args = fixture()
        for changed in (replace(args[1], car_max_age_s=args[1].car_max_age_s+1),
                        replace(args[1], binding=replace(args[1].binding,camera_epoch='changed')),
                        replace(args[1], destination='OFFICE')):
            with self.subTest(changed=changed), self.assertRaises(ExecutionBlocked):
                resume_candidate(args[0], changed, *args[2:])

    def test_unknown_receipt_and_stop_cannot_resume(self):
        args = fixture()
        for receipt in ({**args[-1], 'native_verified':False}, {**args[-1], 'command_id':'foreign'},
                        {**args[-1], 'outcome':'UNKNOWN'}):
            with self.assertRaises(ExecutionBlocked): resume_candidate(*args[:-1], receipt)
        with self.assertRaises(ExecutionBlocked):
            resume_candidate(args[0],args[1],replace(args[2],reason='OPERATOR_STOP'),*args[3:])
        with self.assertRaises(ExecutionBlocked):
            resume_candidate(args[0],args[1],replace(args[2],pending_command_id='unknown'),*args[3:])

    def test_crossing_recontact_and_c14_cannot_resume(self):
        args = fixture()
        with self.assertRaises(ExecutionBlocked):
            resume_candidate(args[0],args[1],replace(args[2],signal_step_index=1),*args[3:])

    def test_state_roundtrip_preserves_lineage(self):
        state = fixture()[2]
        self.assertEqual(state_from_dict(json.loads(json.dumps(asdict(state)))), state)

    def test_hash_chain_corruption_is_rejected(self):
        with TemporaryDirectory() as directory:
            journal=PrivateJournal(Path(directory)); journal.append('proof',{'native_verified':True}); journal.close()
            path=Path(directory)/'events.private.jsonl'
            self.assertEqual(len(read_chain(path)),1)
            path.write_bytes(path.read_bytes().replace(b'true',b'false'))
            with self.assertRaises(ExecutionBlocked): read_chain(path)


class ResumeServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=TemporaryDirectory(); self.store=FakeWorkspace(); self.driver=FakeMeasuredDriver()
        self.service=PhysicalMissionService(self.store,self.temp.name,driver=self.driver,poll_interval_s=.001)
        self.original_command=command_for(self.service,self.store)
        p=self.driver.plan
        self.completed=MissionState(p.id,'session',phase=Phase.OBSERVE,step_index=0,
            action_command_id='done',issued_command_ids=('done',),start_verified=True)
        self.held=replace(self.completed,phase=Phase.FAILED,reason=REVIEW_HOLD)
        self.service.status.update(state='HOLD',mission_id=p.id,error=REVIEW_HOLD)
        self.service._persist('MISSION_ACCEPTED',{'workspace':self.original_command,'policy':asdict(p)})
        self.service._persist('PRIMITIVE_RECEIPT',{'receipt':{'command_id':'done'},'state':asdict(self.completed)})
        self.service._persist('MISSION_HELD',{'state':asdict(self.held)})
        def prepare(*_):
            return p,self.completed,{'summary':'Fresh recovered review'}, {'motion_issued':False}
        self.driver.resume_review=prepare
        self.started=[]
        async def capture(policy,state,command,**kwargs): self.started.append((state,kwargs))
        self.service._run=capture

    async def asyncTearDown(self):
        await self.service.close();self.temp.cleanup()

    def command(self):
        return {'request_id':str(uuid4()),'expected_revision':self.service.status['revision'],
            'mission_id':self.service.status['mission_id'],'reason':'Explicit operator continuation request'}

    async def test_explicit_resume_is_idempotent_keeps_old_error_and_no_replay(self):
        command=self.command();response=await self.service.resume(command)
        await self.service.task
        self.assertEqual(self.driver.commands,[])
        self.assertEqual(self.started[0][0].action_command_id,'done')
        self.assertEqual(response['state'],'OBSERVING')
        self.assertEqual(await self.service.resume(command),response)
        self.assertEqual(len(self.started),1)
        record=json.loads(self.service.db.execute("SELECT value FROM events WHERE kind='MISSION_HELD'").fetchone()[0])
        self.assertEqual(record['state']['reason'],REVIEW_HOLD)

    async def test_failed_scene_check_retains_hold_and_no_retry(self):
        def fail(*_): raise ExecutionBlocked('RESUME_SCENE_CONTINUITY_UNCONFIRMED','changed')
        self.driver.resume_review=fail
        with self.assertRaises(CommandError): await self.service.resume(self.command())
        self.assertEqual(self.service.status['state'],'HOLD')
        self.assertEqual(self.service.status['error'],REVIEW_HOLD)
        with self.assertRaises(CommandError): await self.service.resume(self.command())
        self.assertEqual(self.driver.commands,[])

    async def test_stale_revision_or_foreign_mission_rejected(self):
        for change in ({'expected_revision':0},{'mission_id':'other'}):
            with self.assertRaises(CommandError): await self.service.resume({**self.command(),**change})

    async def test_provider_failure_allows_one_explicit_recheck_but_not_a_loop(self):
        from backend.scene import SceneError
        calls=[]
        def fail(*_):
            calls.append(1)
            raise SceneError(502,'No decision accepted','MUSE_FAILED')
        self.driver.resume_review=fail
        for _ in range(3):
            with self.assertRaises(CommandError): await self.service.resume(self.command())
        self.assertEqual(len(calls),2)
        self.assertEqual(self.driver.commands,[])

    async def test_stop_during_preparation_prevents_continuation(self):
        original=self.driver.resume_review
        def stopped(*args):
            self.service.stop_generation+=1
            return original(*args)
        self.driver.resume_review=stopped
        with self.assertRaises(CommandError): await self.service.resume(self.command())
        self.assertEqual(self.started,[])
        self.assertEqual(self.service.status['state'],'HOLD')
