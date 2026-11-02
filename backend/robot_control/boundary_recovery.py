"""Explicit C11 rollback recovery; preparation never dispatches a route action."""
from copy import deepcopy
from dataclasses import asdict, replace
from pathlib import Path
import asyncio

from .mission_catalog import content_hash
from .mission_resume import require, read_chain, original_frame, review_continuity
from .mission_policy import Phase, MissionPolicy, DecisionKind
from .wrist_commissioning import local_wrist_pose


def apply_boundary_reference(packet, review, record):
    """Resolve reconnect precision at an observed boundary, not an invented START."""
    require(record['schema'] == 'pushpilot.c11-boundary-recovery.v1', 'BOUNDARY_SCHEMA')
    nominal = packet['contexts'][record['context_id']]['pose_base']
    actual = record['anchor_native']['tcp_base']
    require(nominal == record['return']['original_C11_endpoint']
            and record['return']['target'] == record['return']['native']['tcp_base']
            and record['return']['target'][:2] == nominal[:2]
            and all(abs(a-b) <= .005 for a,b in zip(actual, nominal)), 'BOUNDARY_PRECISION_CHANGED')
    require(record['return']['receipt']['endpoint_verified'] is True
            and record['return']['native']['held_disarmed_idle'] is True,
            'BOUNDARY_NATIVE_REQUIRED')
    anchor = record['anchor_native']
    require(anchor['held_disarmed_idle'] is True and len(anchor['native_tcp_base'])==6
            and len(anchor['native_evidence_sha256'])==64
            and all(abs(a-b)<=.100001 for a,b in zip(anchor['native_tcp_base'],actual)), 'BOUNDARY_NATIVE_REQUIRED')
    start = packet['contexts'][packet['routes']['C']['start_context_id']]['pose_base']
    old = [start]
    for _ in range(2):
        old.append(local_wrist_pose(old[-1], -89.999))
    require(nominal[3:] == old[1][3:], 'BOUNDARY_POSTURE_FAMILY')
    new = [local_wrist_pose(actual, 89.999), actual, local_wrist_pose(actual, -89.999)]
    def pose(p):
        matches = [n for o,n in zip(old,new) if max(abs(a-b) for a,b in zip(p[3:],o[3:])) < 1e-6]
        require(len(matches) == 1, 'BOUNDARY_UNKNOWN_POSTURE')
        result = (actual[:2] if p == nominal else p[:2]) + [actual[2]] + matches[0][3:]
        require(all(abs(a-b) <= .005 for a,b in zip(p,result)), 'BOUNDARY_PRECISION_CHANGED')
        return result
    result, updated = deepcopy(packet), deepcopy(review)
    for c in result['contexts'].values():
        c['pose_base'] = pose(c['pose_base'])
    for p in result['primitives'].values():
        for s in p['stages']:
            s['start_base'], s['target_base'] = pose(s['start_base']), pose(s['target_base'])
        p['geometry_sha256'] = content_hash({'kind':p['kind'],
            'stages':[{k:s[k] for k in ('phase','start_base','target_base')} for s in p['stages']],
            'source':p['source_context_id'], 'target':p['target_context_id'],
            'contact_travel_limit_mm':p.get('contact_travel_limit_mm',20.)})
    updated['site']['fixed_tcp_z_mm'] = actual[2]
    updated['operator_authorization_sha256'] = content_hash(record)
    updated['review_reference'] = record['review_reference']
    updated['allowed_geometry_sha256'] = sorted({p['geometry_sha256'] for p in result['primitives'].values()})
    return result, updated


def boundary_state(old_plan, new_plan, interrupted, session_id):
    """Only the failed C12 approach can restart after an evidenced C11 rollback."""
    require(old_plan.destination == 'VILLA' and interrupted.step_index == 11
            and interrupted.phase == Phase.IN_FLIGHT and interrupted.pending_role == 'ROUTE'
            and interrupted.start_verified and not interrupted.vehicle_delivered
            and interrupted.signal_step_index is None and interrupted.admitted_signal_step_index is None
            and old_plan.steps[10].id == 'C-step-11' and old_plan.steps[11].id == 'C-step-12'
            and interrupted.pending_primitive_id == old_plan.steps[11].primitive.id,
            'BOUNDARY_CURSOR_UNSUPPORTED')
    def semantics(value):
        if isinstance(value, dict):
            return {k:semantics(v) for k,v in value.items()
                    if k not in {'qualification_sha256','current_site_review_sha256','calibration_id'}}
        if isinstance(value, (list,tuple)):
            return [semantics(v) for v in value]
        return value
    plan = replace(new_plan, id=old_plan.id)
    require(semantics(asdict(old_plan)) == semantics(asdict(plan)), 'BOUNDARY_POLICY_CHANGED')
    require(interrupted.pending_command_id in interrupted.issued_command_ids, 'BOUNDARY_ISSUED_ID_MISSING')
    state = replace(interrupted, session_id=session_id, phase=Phase.READY,
        pending_command_id=None, pending_primitive_id=None, pending_target_context_id=None,
        pending_role=None, pending_since_s=None, resume_phase=None, reason='EXPLICIT_C11_ROLLBACK', reobservations=0)
    return plan, state


def prepare(driver, workspace, old_plan, interrupted):
    """Verify immutable rollback/transport evidence, fresh Native and car continuity."""
    from .mission_driver import WORKSPACE_KEYS, _StopAwareAPI
    from .legacy import load_runtime
    from .mission_profile import ReviewedProfilePreparer
    from .taught_executor import checked_snapshot
    require(driver.execution_lock.acquire(blocking=False), 'MISSION_BUSY')
    stop_generation = driver._stop_generation
    driver.stop_latch.set()
    try:
        driver._load()  # Explicit, hash-bound recovery deployment; no automatic reload.
        require(not driver._configuration_error, 'BOUNDARY_CONFIGURATION_INVALID')
        record = driver.boundary_recovery
        require(record and record['mission_id'] == old_plan.id
                and record['failed_command_id'] == interrupted.pending_command_id, 'BOUNDARY_MISSION_CHANGED')
        root = Path(driver.config['journal_root'])
        if driver.journal is None:
            driver.journal = driver.journal_factory(root)
        journal = driver.journal
        chain = read_chain(root/'events.private.jsonl')
        endpoints = [r['payload'] for r in chain if r['kind']=='mission_stage_endpoint'
                     and r['payload']['command_id']==record['failed_command_id']]
        intents = [r['payload'] for r in chain if r['kind']=='mission_stage_intent'
                   and r['payload']['command_id']==record['failed_command_id']]
        require(len(endpoints)==1 and endpoints[0]['stage_index']==0
                and len(intents)==2 and all(i['phase']=='approach' for i in intents)
                and endpoints[0]==record['connection']['completed_endpoint']
                and intents[0]==record['connection']['executed_stage'], 'BOUNDARY_PARTIAL_CHANGED')
        # The old unsent mailbox is evidence, never a source of new commands.
        connection = record['connection']
        import json
        run = Path(connection['original_run'])
        summary = json.loads((run/'summary.json').read_bytes())
        events = [json.loads(line) for line in (run/'events.jsonl').read_bytes().splitlines()]
        require(summary['in_flight'] is None and summary['motion_permission_may_have_been_sent'] is False
                and not any(e['kind']=='tx' and e['data'].get('request_id')==connection['unknown_wire']['request_id'] for e in events),
                'BOUNDARY_UNSENT_PROOF_REQUIRED')
        probe = driver.port_factory(adapter=driver.coordinate_binding,journal=journal,**driver.config['ports'])
        raw = probe.api
        terminal = raw.call('/v1/commands/'+connection['unknown_api_request_id'])
        require(terminal['state']=='reconciled' and record['reconcile']['state']=='reconciled', 'BOUNDARY_OUTCOME_UNRESOLVED')
        native = checked_snapshot(probe,driver.coordinate_binding,5.)
        saved = record['anchor_native']
        require(native.session_id==saved['session_id'] and list(native.tcp_base)==saved['tcp_base']
                and native.sequence==saved['sequence'] and native.profile_id==saved['profile_id'], 'BOUNDARY_SOURCE_CHANGED')
        driver._reset_stationary_status(probe._status())
        context = record['context_id']
        require(driver.config['contexts'][context]['pose_base']==list(native.tcp_base), 'BOUNDARY_CONTEXT_CHANGED')
        candidates = [p for key,p in driver.routes if all(workspace[k]==key[k] for k in WORKSPACE_KEYS)]
        require(len(candidates)==1, 'BOUNDARY_ROUTE_CHANGED')
        plan,state = boundary_state(old_plan,candidates[0],interrupted,native.session_id)
        require(plan.steps[11].primitive.source_context_id==context, 'BOUNDARY_NEXT_SOURCE_CHANGED')
        camera = probe._camera_status()
        previous_camera = record['camera']
        require(camera['epoch']==previous_camera['epoch'] and all(camera['registration'][k]==previous_camera['registration'][k]
                for k in ('homography','reference_frame_id')), 'BOUNDARY_CAMERA_CHANGED')
        # Compare the actual last C11 review frame, not a fabricated observation.
        originals = []
        for path in root.glob('mission-observation-*.private.json'):
            value = json.loads(path.read_bytes())
            if value.get('task',{}).get('action_command_id')==state.action_command_id:
                originals.append(value)
        require(bool(originals), 'BOUNDARY_C11_IMAGE_MISSING')
        original = max(originals,key=lambda v:v['frame']['captured_at'])
        held = original_frame(root,original['frame'])
        current = probe.capture()
        continuity = asyncio.run(review_continuity(driver.observer_callback.provider,held,current))
        journal.artifact('boundary-continuity',{'original':held.metadata(),'current':current.metadata(),'result':continuity})
        require(all(continuity[k] is True for k in ('car_visible_in_both','car_position_unchanged',
                'car_orientation_unchanged','board_view_unchanged')) and continuity['clear_problem'] is False,
                'BOUNDARY_CAR_CONTINUITY_UNCONFIRMED')
        fresh = checked_snapshot(probe,driver.coordinate_binding,5.)
        require(fresh.session_id==native.session_id and fresh.tcp_base==native.tcp_base
                and fresh.sequence==native.sequence and fresh.profile_id==native.profile_id,'BOUNDARY_SOURCE_CHANGED')
        driver._pin(probe._status())
        driver.ports,driver.raw_api = probe,raw
        probe.api = _StopAwareAPI(raw,driver.stop_latch,driver._validate_profile)
        driver.profile_preparer = ReviewedProfilePreparer(api=lambda p,v=None:raw.call(p,v),journal=journal,
            native_snapshot=lambda:checked_snapshot(probe,driver.coordinate_binding,5.),
            receiver_policy=load_runtime(Path(driver.config['ports']['runtime']))['policy'], stop_check=driver._not_stopped)
        driver.currentplan=driver.plan=plan
        driver.workspace_binding=dict(workspace)
        driver.current_context_id=context
        driver.pending_command_id=None
        driver.issued.update(state.issued_command_ids)
        driver.last_snapshot=fresh
        # Query the actual next unit's current/target IK without dispatching it.
        # The preparation lock excludes another worker; a concurrent Stop still
        # cancels this bounded read-only/profile operation through the latch.
        from uuid import uuid4
        with driver._stop_lock:
            require(driver._stop_generation==stop_generation, 'BOUNDARY_STOPPED')
            driver.stop_latch.clear()
        try:
            driver._prepare_measured(plan.steps[11].primitive.id,'boundary-readonly-'+uuid4().hex)
            fresh=driver._snapshot()
        finally:
            driver.stop_latch.set()
        proof={'native':asdict(fresh),'continuity':continuity,'next_step':'C-step-12','motion_issued':False,
               'command_replayed':False,'failed_command_id':record['failed_command_id'],'automatic_resume':False}
        journal.append('explicit_boundary_prepared',proof)
        journal.checkpoint({'state':'BOUNDARY_RECOVERY_PREPARED','mission_id':plan.id,'proof':proof})
        driver._prepared_boundary=(plan,state,proof)
        return plan,state,proof
    finally:
        driver.stop_latch.set()
        driver.execution_lock.release()


def activate(driver):
    """A separate explicit resume rechecks the source; no re-PLAY recovery here."""
    require(hasattr(driver,'_prepared_boundary'), 'BOUNDARY_PREPARATION_REQUIRED')
    plan,state,proof=driver._prepared_boundary
    fresh=driver._snapshot()
    previous=proof['native']
    require(fresh.session_id==previous['session_id'] and fresh.sequence==previous['sequence']
            and fresh.profile_id==previous['profile_id'] and tuple(fresh.tcp_base)==tuple(previous['tcp_base']),
            'BOUNDARY_SOURCE_CHANGED')
    driver.ports._camera_status()
    driver.stop_latch.clear()
    decision=MissionPolicy(plan).decide(state,driver.context(),command_id='boundary-preflight-only')
    if decision.kind!=DecisionKind.DISPATCH or decision.primitive_id!=plan.steps[11].primitive.id:
        driver.stop_latch.set()
        require(False,'BOUNDARY_NEXT_ACTION_BLOCKED')
    del driver._prepared_boundary
    return plan,state,proof


def restore_prepared(driver, workspace, plan, state, proof):
    """Revalidate a durable preparation on an explicit resume, never on startup."""
    from .mission_driver import WORKSPACE_KEYS
    require(driver.execution_lock.acquire(blocking=False), 'MISSION_BUSY')
    driver.stop_latch.set()
    try:
        driver._load()
        require(state.phase==Phase.READY and state.step_index==11 and state.pending_command_id is None
                and proof['motion_issued'] is False and proof['next_step']=='C-step-12', 'BOUNDARY_CURSOR_UNSUPPORTED')
        candidates=[p for key,p in driver.routes if all(key[k]==workspace[k] for k in WORKSPACE_KEYS)]
        require(len(candidates)==1,'BOUNDARY_ROUTE_CHANGED')
        current=replace(candidates[0],id=plan.id)
        permitted=replace(plan,binding=replace(plan.binding,calibration_id=current.binding.calibration_id))
        require(asdict(current)==asdict(permitted),'BOUNDARY_POLICY_CHANGED')
        driver._ensure_ports()
        checkpoint=driver.journal.load()
        require(checkpoint['state']=='BOUNDARY_RECOVERY_PREPARED'
                and checkpoint['mission_id']==plan.id and checkpoint['proof']==proof,'BOUNDARY_CHECKPOINT_CHANGED')
        chain=read_chain(Path(driver.config['journal_root'])/'events.private.jsonl')
        saved=[row for row in chain if row['kind']=='explicit_boundary_prepared']
        require(saved and saved[-1]['payload']==proof,'BOUNDARY_PREPARATION_EVIDENCE_CHANGED')
        status=driver.ports._status()
        driver._reset_stationary_status(status)
        driver._pin(status)
        native=driver._snapshot()
        before=proof['native']
        require(native.session_id==before['session_id'] and native.sequence==before['sequence']
                and native.profile_id==before['profile_id'] and list(native.tcp_base)==before['tcp_base']
                and native.installation_id==before['installation_id'],'BOUNDARY_SOURCE_CHANGED')
        camera=driver.ports._camera_status()
        previous=driver.boundary_recovery['camera']
        require(camera['epoch']==previous['epoch'] and all(camera['registration'][k]==previous['registration'][k]
                for k in ('homography','reference_frame_id')),'BOUNDARY_CAMERA_CHANGED')
        # The previous unchanged-car result remains evidence, not a new verdict.
        # Recheck current scene continuity when a web restart separated prepare/run.
        import json
        root=Path(driver.config['journal_root'])
        originals=[]
        for path in root.glob('mission-observation-*.private.json'):
            value=json.loads(path.read_bytes())
            if value.get('task',{}).get('action_command_id')==state.action_command_id:
                originals.append(value)
        require(bool(originals),'BOUNDARY_C11_IMAGE_MISSING')
        original=max(originals,key=lambda v:v['frame']['captured_at'])
        held=original_frame(root,original['frame'])
        frame=driver.capture()
        continuity=asyncio.run(review_continuity(driver.observer_callback.provider,held,frame))
        driver.journal.artifact('boundary-restore-continuity',{'original':held.metadata(),'current':frame.metadata(),'result':continuity})
        require(all(continuity[k] is True for k in ('car_visible_in_both','car_position_unchanged',
            'car_orientation_unchanged','board_view_unchanged')) and continuity['clear_problem'] is False,
            'BOUNDARY_CAR_CONTINUITY_UNCONFIRMED')
        driver.currentplan=driver.plan=current
        driver.workspace_binding=dict(workspace)
        driver.current_context_id=current.steps[11].primitive.source_context_id
        driver.pending_command_id=None
        driver.issued.update(state.issued_command_ids)
        driver._prepared_boundary=(current,state,proof)
        driver.journal.append('explicit_boundary_restored',{'mission_id':current.id,'native':asdict(native),
            'continuity':continuity,'automatic_resume':False,'motion_issued':False})
    finally:
        driver.stop_latch.set()
        driver.execution_lock.release()
