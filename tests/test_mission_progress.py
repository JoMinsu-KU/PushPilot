"""Offline progress-only contracts. No physical calls or acceptance claims."""
import asyncio
import base64
from dataclasses import asdict, replace
import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock

import cv2
import httpx
import numpy as np

from backend.robot_control.mission_progress import (
    PROGRESS_PROMPT, comparison_content, detail_content, observe_progress, validate_progress,
)
from backend.robot_control.mission_vision import MetaMissionVision
from backend.robot_control.mission_policy import MissionPolicy, ParkingTarget, Phase, DecisionKind
from backend.scene import SceneError
from tools.revise_c_progress_review import select_c_progress_review
from tests.test_live_review_provider import envelope
from tests.test_mission_policy import plan, after_first, car, context, signal


def result(**changes):
    return {"status":"PROGRESS_OBSERVED", "car_visible":True, "visible_change":True,
            "clear_problem":False, "occlusion_cause":"NONE", "summary":"Synthetic visible displacement.",
            "limitations":[], **changes}


def image(value=30):
    ok, data = cv2.imencode('.jpg', np.full((80,120,3),value,np.uint8))
    assert ok
    raw=data.tobytes()
    return {"data":raw,"metadata":{"sha256":hashlib.sha256(raw).hexdigest()}}


def trial_plan(gated=False):
    source=plan(signal=True)
    def trial(p):return replace(p,qualified=False,release_mode="site_trial",current_site_review_sha256="a"*64)
    gate=source.steps[0].signal_gate
    gate=replace(gate,recontact=trial(gate.recontact),release_to_wait=trial(gate.release_to_wait)) if gated else None
    steps=(replace(source.steps[0],primitive=trial(source.steps[0].primitive),signal_gate=gate,
                   review_mode="intermediate_progress"),
           replace(source.steps[1],primitive=trial(replace(source.steps[1].primitive,
                   source_context_id="LAST_CONTACT" if gated else "RIGHT_WAIT"))))
    return replace(source,destination="VILLA",steps=steps,parking=ParkingTarget(0,mode="delivery_only"),
                   empty_return=tuple(trial(p) for p in source.empty_return),release_mode="site_trial")


class ProgressContracts(unittest.TestCase):
    def test_contradictory_pass_missing_facts_and_commands_are_rejected(self):
        for changes in ({"visible_change":False},{"visible_change":None},{"clear_problem":True},
                        {"clear_problem":0},{"clear_problem":"false"},{"car_visible":False},{"occlusion_cause":"HOSE"},
                        {"status":"NO_PROGRESS"},{"status":"CLEAR_PROBLEM"},{"robot_command":"move"},
                        {"visible_change":1}):
            with self.subTest(changes=changes),self.assertRaises(SceneError):validate_progress(result(**changes))
        self.assertEqual(validate_progress(result(status="UNCERTAIN",visible_change=None))["status"],"UNCERTAIN")

    def test_unknown_problem_is_preserved_without_inventing_motion_or_visibility(self):
        for status,change in (("PROGRESS_OBSERVED",True),("NO_PROGRESS",False)):
            source=result(status=status,visible_change=change,clear_problem=None)
            parsed=validate_progress(source)
            self.assertEqual(parsed,source)
            self.assertIsNone(parsed['clear_problem'])
        for changes in ({'visible_change':None},{'car_visible':False},{'occlusion_cause':'TOOL'},
                        {'status':'CLEAR_PROBLEM'}):
            with self.subTest(changes=changes),self.assertRaises(SceneError):
                validate_progress(result(clear_problem=None,**changes))

    def test_composite_preserves_every_decoded_source_pixel_and_order(self):
        before,current=image(25),image(190)
        parts=comparison_content(before,current)
        png=base64.b64decode(parts[1]['image_url']['url'].split(',',1)[1])
        composite=cv2.imdecode(np.frombuffer(png,np.uint8),cv2.IMREAD_COLOR)
        self.assertEqual(composite.shape,(140,240,3))
        for index,frame in enumerate((before,current)):
            expected=cv2.imdecode(np.frombuffer(frame['data'],np.uint8),cv2.IMREAD_COLOR)
            np.testing.assert_array_equal(composite[60:,index*120:(index+1)*120],expected)
        self.assertIn(hashlib.sha256(png).hexdigest(),parts[0]['text'])

    def test_absent_or_changed_source_is_rejected(self):
        with self.assertRaises(SceneError):comparison_content(None,image())
        bad=image();bad['metadata']['sha256']='0'*64
        with self.assertRaises(SceneError):comparison_content(bad,image())

    def test_detail_preserves_fixed_native_coordinates_and_full_pair(self):
        before,current=image(25),image(190)
        roi=[10,20,90,70]
        detail=detail_content(before,current,roi)
        raw=base64.b64decode(detail[1]['image_url']['url'].split(',',1)[1])
        decoded=cv2.imdecode(np.frombuffer(raw,np.uint8),cv2.IMREAD_COLOR)
        for i,frame in enumerate((before,current)):
            source=cv2.imdecode(np.frombuffer(frame['data'],np.uint8),cv2.IMREAD_COLOR)
            np.testing.assert_array_equal(decoded[48:,i*80:(i+1)*80],source[20:70,10:90])
        def handler(request):
            content=json.loads(request.content)['messages'][1]['content']
            self.assertEqual(sum(p['type']=='image_url' for p in content),2)
            self.assertIn('reference was captured while stopped',content[-1]['text'])
            return httpx.Response(200,json=envelope(result(clear_problem=None)))
        provider=MetaMissionVision('synthetic',transport=httpx.MockTransport(handler))
        actual=asyncio.run(provider.observe_progress(frame=current,before=before,detail_roi=roi,
            comparison_scope='signal_wait_through_recontact_and_C14'))
        self.assertIsNone(actual['clear_problem'])
        for bad in ([0,0,121,80],[-1,0,20,20],[0,0,0,20],[0,0,10.,20]):
            with self.assertRaises(SceneError):detail_content(before,current,bad)

    def test_c14_reference_requires_exact_mission_session_and_command_interval(self):
        from types import SimpleNamespace
        from tests.test_mission_observer import FakeFrame
        from backend.robot_control.mission_observer import MissionObserver
        from backend.robot_control.taught_executor import ExecutionBlocked
        source=trial_plan(gated=True)
        gate=replace(source.steps[0].signal_gate,entry_policy='single_departure')
        # Lightweight lineage fixture: the real plan's continuity is tested separately.
        fixture=SimpleNamespace(id=source.id,destination='VILLA',binding=source.binding,
            steps=[replace(source.steps[0],id='C-step-13',signal_gate=gate),
                   SimpleNamespace(id='C-step-14')])
        observer=MissionObserver(provider=object())
        before=FakeFrame(10,100.);after=FakeFrame(20,600.)
        ctx=context('RIGHT_WAIT',600.,10)
        state=replace(after_first(MissionPolicy(source)),step_index=1,signal_step_index=0,
            issued_command_ids=('previous','recontact','c14'),action_command_id='c14')
        observer.signal_progress_references[(source.id,0)]=(before,ctx,('previous',))
        self.assertIs(observer._c14_reference(state,fixture,after,ctx),before)
        for changed in (replace(state,issued_command_ids=('previous','extra','recontact','c14')),
                        replace(state,action_command_id='different'),replace(state,signal_step_index=None)):
            with self.assertRaises(ExecutionBlocked):observer._c14_reference(changed,fixture,after,ctx)
        with self.assertRaises(ExecutionBlocked):
            observer._c14_reference(state,fixture,after,replace(ctx,session_id='different'))
        with self.assertRaises(ExecutionBlocked):
            observer._c14_reference(state,fixture,FakeFrame(30,1401.),ctx)
        with self.assertRaises(ExecutionBlocked):
            observer._c14_reference(state,fixture,FakeFrame(30,700.,epoch='other'),ctx)
        fixture.id='different-mission'
        with self.assertRaises(ExecutionBlocked):observer._c14_reference(state,fixture,after,ctx)

    def test_provider_has_no_angle_zone_signal_or_success_hint_context(self):
        calls=[]
        def handler(request):
            body=json.loads(request.content);calls.append(body)
            self.assertEqual(body['messages'][0]['content'],PROGRESS_PROMPT)
            self.assertEqual(sum(p['type']=='image_url' for p in body['messages'][1]['content']),1)
            self.assertNotIn('expected_heading_deg',request.content.decode())
            return httpx.Response(200,json=envelope(result()))
        provider=MetaMissionVision('synthetic',transport=httpx.MockTransport(handler))
        actual=asyncio.run(observe_progress(provider,frame=image(90),before=image()))
        self.assertEqual(actual,result());self.assertEqual(len(calls),1)


class ProgressPolicyTests(unittest.TestCase):
    def setup_observation(self,gated=False):
        policy=MissionPolicy(trial_plan(gated));state=after_first(policy);at=context('RIGHT_WAIT',12,2)
        observation=car(at,state,step='approach',zone=None,within_road=None,heading_matches_expected=False,
            heading_deg=None,heading_uncertainty_deg=None,measurement_source='unmeasured',
            measurement_evidence_sha256=None,arrived=False,progress_status='PROGRESS_OBSERVED',
            visible_change=True,clear_problem=False)
        return policy,state,at,observation

    def test_progress_does_not_invent_road_heading_or_zone(self):
        policy,state,at,observation=self.setup_observation()
        decision=policy.decide(state,at,car=observation,command_id='next')
        self.assertEqual(decision.kind,DecisionKind.DISPATCH)
        self.assertEqual(decision.primitive_id,'crossing-unit')
        self.assertIsNone(observation.within_road)
        self.assertFalse(observation.heading_matches_expected)

    def test_printed_overlap_does_not_fail_opt_in_intermediate_review(self):
        policy,state,at,observation=self.setup_observation()
        decision=policy.decide(state,at,car=replace(observation,within_road=False),command_id='next')
        self.assertEqual(decision.kind,DecisionKind.DISPATCH)

    def test_no_progress_uncertain_problem_and_inconsistent_pass_never_dispatch(self):
        for changes in ({'progress_status':'NO_PROGRESS','visible_change':False,'verdict':'FAIL'},
                        {'progress_status':'UNCERTAIN','visible_change':None,'verdict':'UNCERTAIN'},
                        {'progress_status':'CLEAR_PROBLEM','clear_problem':True,'verdict':'FAIL'},
                        {'progress_status':None},{'visible_change':False},{'clear_problem':True},
                        {'verdict':'FAIL'},{'car_visible':False},{'occlusion_cause':'HOSE'}):
            policy,state,at,observation=self.setup_observation()
            decision=policy.decide(state,at,car=replace(observation,**changes),command_id='next')
            self.assertNotEqual(decision.kind,DecisionKind.DISPATCH)
            self.assertNotIn('MEASURED_CORRECTION',decision.reason)

    def test_unknown_problem_alone_allows_visible_progress_without_coercion(self):
        policy,state,at,observation=self.setup_observation()
        observation=replace(observation,clear_problem=None)
        decision=policy.decide(state,at,car=observation,command_id='next')
        self.assertEqual(decision.kind,DecisionKind.DISPATCH)
        self.assertIsNone(observation.clear_problem)

    def test_unknown_problem_does_not_override_other_blockers(self):
        for changes in ({'visible_change':None},{'car_visible':False},{'occlusion_cause':'TOOL'},
                        {'progress_status':'UNCERTAIN','verdict':'UNCERTAIN'},
                        {'progress_status':'NO_PROGRESS','visible_change':False,'verdict':'FAIL'},
                        {'captured_at_s':13.}, {'action_command_id':'other'}):
            policy,state,at,observation=self.setup_observation()
            decision=policy.decide(state,at,car=replace(observation,clear_problem=None,**changes),command_id='next')
            with self.subTest(changes=changes):self.assertNotEqual(decision.kind,DecisionKind.DISPATCH)
        policy,state,at,observation=self.setup_observation()
        stale=policy.decide(state,replace(at,now_s=50.,native_observed_at_s=50.),
            car=replace(observation,clear_problem=None),command_id='next')
        self.assertNotEqual(stale.kind,DecisionKind.DISPATCH)
        policy,state,at,observation=self.setup_observation(gated=True)
        observation=replace(observation,clear_problem=None)
        decision=policy.decide(state,at,car=observation,command_id='next')
        self.assertEqual(decision.state.phase,Phase.WAIT_SIGNAL)
        waiting=policy.decide(decision.state,at,car=observation,signal=signal(at,color='RED'),command_id='next')
        self.assertEqual(waiting.kind,DecisionKind.WAIT)

    def test_stale_native_and_changed_session_still_block(self):
        for changes in ({'session_id':'other'},{'stationary':False},{'tool_clear':False}):
            policy,state,at,observation=self.setup_observation()
            decision=policy.decide(state,replace(at,**changes),car=observation,command_id='next')
            self.assertEqual(decision.kind,DecisionKind.HOLD)

    def test_signal_stop_is_not_bypassed_by_car_progress(self):
        policy,state,at,observation=self.setup_observation(gated=True)
        decision=policy.decide(state,at,car=observation,command_id='next')
        self.assertEqual(decision.state.phase,Phase.WAIT_SIGNAL)
        self.assertNotEqual(decision.kind,DecisionKind.DISPATCH)
        waiting=policy.decide(decision.state,at,car=observation,signal=signal(at,color='RED'),command_id='next')
        self.assertEqual(waiting.kind,DecisionKind.WAIT)

    def test_final_and_qualified_modes_cannot_enable_progress_only(self):
        config=trial_plan()
        with self.assertRaises(ValueError):replace(config.steps[-1],review_mode='intermediate_progress')
        with self.assertRaises(ValueError):replace(config,release_mode='qualified')

    def test_candidate_changes_only_c_intermediate_policy(self):
        p=asdict(trial_plan());p['steps'][0]['id']='C-step-1';p['steps'][1]['id']='C-step-26'
        b=asdict(plan());b['destination']='OFFICE'
        original={'routes':[{'plan':p},{'plan':b}],'coordinate_sentinel':[1,2,3]}
        candidate,selected=select_c_progress_review(original)
        self.assertEqual(selected,['C-step-1'])
        self.assertEqual(candidate['routes'][1],original['routes'][1])
        self.assertEqual(candidate['routes'][0]['plan']['steps'][-1],original['routes'][0]['plan']['steps'][-1])

    def test_raw_site_override_loads_only_c_and_preserves_geometry(self):
        from copy import deepcopy
        from tests.test_site_trial_driver import fixture, save_artifact
        from backend.robot_control.site_trial_driver import SiteTrialMissionDriver
        with TemporaryDirectory() as directory:
            path, config, packet, _, _ = fixture(Path(directory))
            packet['routes']['C'] = deepcopy(packet['routes']['B'])
            packet['routes']['C']['destination'] = 'VILLA'
            packet['routes']['C']['steps'][0]['id'] = 'C-step-26'
            intermediate = deepcopy(packet['routes']['C']['steps'][0])
            intermediate.update(id='C-step-1', at_goal=False)
            packet['routes']['C']['steps'].insert(0, intermediate)
            reposition=deepcopy(intermediate)
            reposition.update(id='C-step-2',primitive_id='return')
            packet['routes']['C']['steps'].insert(1,reposition)
            config['workspace_bindings']['C'] = {**config['workspace_bindings']['B'],
                'destination':'VILLA', 'route_nodes':['PIZZA','VILLA']}
            save_artifact(config['packet'], packet)
            baseline=deepcopy(config)
            candidate,_=select_c_progress_review(config)
            self.assertEqual(config,baseline)
            path.write_text(json.dumps(candidate))
            ports=Mock(side_effect=AssertionError('No device access during config load'))
            driver=SiteTrialMissionDriver(path,port_factory=ports)
            self.assertIsNone(driver._configuration_error)
            modes={binding['destination']:[s.review_mode for s in plan.steps] for binding,plan in driver.routes}
            self.assertEqual(modes['VILLA'],['intermediate_progress','expected_outcome','expected_outcome'])
            self.assertEqual(modes['OFFICE_BUILDING'],['expected_outcome'])
            self.assertEqual(driver.config['packet'],baseline['packet'])
            ports.assert_not_called()

    def test_observer_uses_progress_only_after_start_and_retains_signal_reference(self):
        from tests.test_mission_observer import ObserverDriver, FakeProvider, FakeFrame, FakeMeasurement
        from backend.robot_control.mission_observer import MissionObserver
        class Provider(FakeProvider):
            async def observe_progress(self, *, frame, before):
                self.calls.append(('progress', {'frame':frame,'before':before}))
                return result(clear_problem=None)
        driver=ObserverDriver();driver.plan=trial_plan(gated=True)
        provider=Provider();measurement=FakeMeasurement()
        observer=MissionObserver(provider=provider,measurement=measurement,sleep=lambda _:None)
        state=after_first(MissionPolicy(driver.plan))
        driver.prepare_frames(FakeFrame(10,100.))
        reviewed=observer(state,driver)
        self.assertEqual(provider.calls[0][0],'progress')
        self.assertEqual(reviewed['car'].progress_status,'PROGRESS_OBSERVED')
        self.assertIsNone(reviewed['car'].clear_problem)
        self.assertIsNone(reviewed['car'].within_road)
        self.assertEqual(measurement.calls,[])
        self.assertIn((driver.plan.id,driver.plan.steps[0].id),observer.last_car_frames)
        driver.prepare_frames(FakeFrame(20,110.),FakeFrame(21,110.4))
        observer(replace(state,phase=Phase.WAIT_SIGNAL,signal_step_index=0),driver)
        self.assertEqual([c[0] for c in provider.calls],['progress','signal'])
        driver.prepare_frames(FakeFrame(30,120.))
        observer(replace(state,start_verified=False),driver)
        self.assertEqual(provider.calls[-1][0],'car')

    def test_c14_observer_uses_latest_visible_green_frame_and_journals_interval(self):
        from tests.test_mission_observer import ObserverDriver, FakeProvider, FakeFrame
        from backend.robot_control.mission_observer import MissionObserver
        class Provider(FakeProvider):
            async def observe_progress(self, **options):
                self.calls.append(('progress',options))
                return result(clear_problem=None)
        source=trial_plan(gated=True)
        first=replace(source.steps[0],id='C-step-13',
            signal_gate=replace(source.steps[0].signal_gate,entry_policy='single_departure'))
        second=replace(source.steps[1],id='C-step-14',at_goal=False,review_mode='intermediate_progress')
        final=replace(source.steps[1],id='C-step-26',
            primitive=replace(source.steps[1].primitive,id='final',source_context_id='GOAL_PARK'))
        driver=ObserverDriver();driver.plan=replace(source,steps=(first,second,final))
        driver.observation_config['c14_clear_signal_reference']=True
        provider=Provider();observer=MissionObserver(provider=provider,sleep=lambda _:None)
        state=replace(after_first(MissionPolicy(source)),issued_command_ids=('previous',),phase=Phase.WAIT_SIGNAL)
        observer.last_car_frames[(driver.plan.id,first.id)]=FakeFrame(5,90.)
        driver.prepare_frames(FakeFrame(10,100.),FakeFrame(11,100.4))
        observer(state,driver)
        state=replace(state,phase=Phase.OBSERVE,step_index=1,signal_step_index=0,
            issued_command_ids=('previous','recontact','c14'),action_command_id='c14')
        driver.prepare_frames(FakeFrame(20,600.),sequence=3)
        observer(state,driver)
        kind,options=provider.calls[-1]
        self.assertEqual(kind,'progress')
        self.assertEqual(options['before']['metadata']['sequence'],11)
        self.assertEqual(options['comparison_scope'],'signal_wait_through_recontact_and_C14')
        self.assertEqual(driver.journal.entries[-1][1]['task']['comparison_scope'],options['comparison_scope'])
        self.assertIsNone(driver.journal.entries[-1][1]['result']['clear_problem'])


if __name__=='__main__':unittest.main()
