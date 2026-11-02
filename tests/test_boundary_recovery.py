"""No-hardware regression tests for an explicitly restored C11 boundary."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from backend.robot_control.boundary_recovery import apply_boundary_reference,boundary_state
from backend.robot_control.wrist_commissioning import local_wrist_pose
from backend.robot_control.mission_policy import MissionState,Phase
from backend.robot_control.taught_executor import ExecutionBlocked
from tests.test_site_trial_driver import fixture
from tests.test_mission_resume import fixture as mission_fixture

class BoundaryTests(unittest.TestCase):
    def test_fixed_xy_and_limits_with_explicit_precision_only_anchor(self):
        with TemporaryDirectory() as d:
            _,_,packet,review,_=fixture(Path(d))
        packet['routes']['C']=deepcopy(next(iter(packet['routes'].values())))
        start=packet['contexts']['START']['pose_base']
        north=local_wrist_pose(start,-89.999)
        north[:2]=[25.,26.]
        packet['contexts']['BOUNDARY']={'pose_base':north,'tool_clear':True}
        actual=list(north);actual[2]+=.001
        native={'tcp_base':actual,'held_disarmed_idle':True,'native_tcp_base':actual,'native_evidence_sha256':'a'*64}
        record={'schema':'pushpilot.c11-boundary-recovery.v1','context_id':'BOUNDARY',
            'return':{'original_C11_endpoint':north,'target':north,'native':{'tcp_base':north,'held_disarmed_idle':True},
                      'receipt':{'endpoint_verified':True}},'anchor_native':native,'review_reference':'synthetic'}
        original=deepcopy(packet)
        result,bound=apply_boundary_reference(packet,review,record)
        self.assertEqual(packet,original)
        self.assertEqual(result['contexts']['BOUNDARY']['pose_base'],actual)
        for k,p in result['primitives'].items():
            for a,b in zip(p['stages'],packet['primitives'][k]['stages']):
                self.assertEqual(a['start_base'][:2],b['start_base'][:2])
                self.assertEqual(a['target_base'][:2],b['target_base'][:2])
        for k in ('max_speed_mm_s','max_accel_mm_s2','max_step_mm','workspace_min_mm','workspace_max_mm'):
            self.assertEqual(bound[k],review[k])
        actual[2]+=.02
        with self.assertRaises(ExecutionBlocked):apply_boundary_reference(packet,review,record)

    def test_cursor_preserves_used_command_and_never_skips_c12_or_signal(self):
        old,_,_,_,_=mission_fixture()
        template=old.steps[2]
        steps=tuple(replace(template,id=f'C-step-{i+1}',primitive=replace(template.primitive,id=f'p{i}',source_context_id=old.start_context_id if i==0 else f'node{i}',target_context_id=f'node{i+1}')) for i in range(12))+(replace(old.steps[-1],primitive=replace(old.steps[-1].primitive,source_context_id='node12')),)
        old=replace(old,steps=steps)
        state=MissionState(old.id,'old-session',phase=Phase.IN_FLIGHT,step_index=11,start_verified=True,
            pending_command_id='failed',pending_primitive_id=steps[11].primitive.id,pending_role='ROUTE',
            pending_target_context_id=steps[11].primitive.target_context_id,issued_command_ids=('completed','failed'),
            action_command_id='completed')
        new,s=boundary_state(old,old,state,'new-session')
        self.assertEqual(s.step_index,11)
        self.assertEqual(s.issued_command_ids,state.issued_command_ids)
        self.assertIsNone(s.pending_command_id)
        self.assertIsNone(s.signal_step_index)
        self.assertEqual(s.phase,Phase.READY)
        self.assertEqual(state.phase,Phase.IN_FLIGHT)
        for bad in (replace(state,step_index=10),replace(state,signal_step_index=9),replace(state,pending_role='RECONTACT')):
            with self.assertRaises(ExecutionBlocked):boundary_state(old,old,bad,'new')
        with self.assertRaises(ExecutionBlocked):boundary_state(old,replace(old,car_max_age_s=old.car_max_age_s+1),state,'new')


class PreparationServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_prepare_keeps_hold_never_starts_worker_and_deduplicates(self):
        from dataclasses import asdict
        from unittest.mock import patch
        from uuid import uuid4
        from backend.physical_mission import PhysicalMissionService
        from tests.test_physical_mission import FakeWorkspace,FakeMeasuredDriver,command_for
        from backend.core import CommandError
        old,_,_,_,_=mission_fixture()
        template=old.steps[2]
        steps=tuple(replace(template,id=f'C-step-{i+1}',primitive=replace(template.primitive,id=f'p{i}',source_context_id=old.start_context_id if i==0 else f'node{i}',target_context_id=f'node{i+1}')) for i in range(12))+(replace(old.steps[-1],primitive=replace(old.steps[-1].primitive,source_context_id='node12')),)
        old=replace(old,steps=steps)
        state=MissionState(old.id,'session',phase=Phase.IN_FLIGHT,step_index=11)
        with TemporaryDirectory() as folder:
            store=FakeWorkspace();driver=FakeMeasuredDriver(old)
            service=PhysicalMissionService(store,Path(folder),driver=driver)
            try:
                workspace=command_for(service,store)
                service.status.update(state='HOLD',error='ROBOT_NOT_COMPLETE',mission_id=old.id)
                service._persist('MISSION_ACCEPTED',{'policy':asdict(old),'workspace':workspace})
                service._persist('MISSION_INTERRUPTED',{'state':asdict(state)})
                command={'request_id':str(uuid4()),'expected_revision':service.status['revision'],
                         'mission_id':old.id,'reason':'Prepare the explicit boundary without movement.'}
                proof={'motion_issued':False,'automatic_resume':False}
                with patch('backend.robot_control.boundary_recovery.prepare',return_value=(old,state,proof)) as prepare:
                    response=await service.prepare_boundary(command)
                    duplicate=await service.prepare_boundary(command)
                    self.assertEqual(response,duplicate)
                    self.assertEqual(prepare.call_count,1)
                self.assertEqual(response['state'],'HOLD')
                self.assertEqual(response['error'],'BOUNDARY_READY')
                self.assertIsNone(service.task)
                self.assertEqual(driver.commands,[])
                with self.assertRaises(CommandError):
                    await service.prepare_boundary({**command,'request_id':str(uuid4())})
            finally:
                await service.close()


class ActivationTests(unittest.TestCase):
    def test_live_tuple_and_durable_list_sources_both_match_without_weakening_values(self):
        from types import SimpleNamespace
        from threading import Event
        from unittest.mock import patch
        from backend.robot_control.boundary_recovery import activate
        from backend.robot_control.mission_policy import DecisionKind
        for kind in (tuple,list):
            native=SimpleNamespace(session_id='same',sequence=13,profile_id='same-profile',tcp_base=(1.,2.,3.,4.,5.,6.))
            proof={'native':{'session_id':'same','sequence':13,'profile_id':'same-profile','tcp_base':kind(native.tcp_base)}}
            p=SimpleNamespace(steps=[None]*11+[SimpleNamespace(primitive=SimpleNamespace(id='C12'))])
            driver=SimpleNamespace(_prepared_boundary=(p,object(),proof),_snapshot=lambda:native,
                ports=SimpleNamespace(_camera_status=lambda:None),stop_latch=Event(),context=lambda:object())
            decision=SimpleNamespace(kind=DecisionKind.DISPATCH,primitive_id='C12')
            with patch('backend.robot_control.boundary_recovery.MissionPolicy') as policy:
                policy.return_value.decide.return_value=decision
                activate(driver)
            self.assertFalse(hasattr(driver,'_prepared_boundary'))
            driver._prepared_boundary=(p,object(),proof)
            proof['native']['tcp_base']=[1.,2.,3.,4.,5.,6.00001]
            with self.assertRaises(ExecutionBlocked):activate(driver)
