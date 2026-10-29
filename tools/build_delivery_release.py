"""Compile private delivery candidates into a portable, reviewable site trial.

This is an offline compiler, not a physical qualification or command sender.
Original receipts remain provenance; runtime commands must receive fresh IDs,
Native source checks, current-profile checks and a current-site review binding.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.robot_control.mission_catalog import content_hash
from backend.robot_control.tcp_path import split_fixed_pose_tcp_segment
from backend.robot_control.wrist_commissioning import local_wrist_pose


DESTINATIONS = {"B": "OFFICE_BUILDING", "C": "VILLA", "D": "HANOK"}
PHASES = {"approach", "contact", "withdraw", "empty", "wrist"}
ZERO_SHA = "0" * 64


def _pose(value):
    if (not isinstance(value, (list, tuple)) or len(value) != 6
            or any(type(x) not in (int, float) or not math.isfinite(x) for x in value)):
        raise ValueError("A pose must contain six finite numeric components.")
    return list(value)


def _sha(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError("An original SHA-256 is required.")
    return value


def _near(a, b, tolerance=1e-9):
    return len(a) == len(b) and all(abs(x-y) <= tolerance for x, y in zip(a, b))


def verify_original_evidence(bundle):
    """Check each original container/member once; no network or device access."""
    refs = {}
    for unit in _units(bundle).values():
        for ref in unit.get("source_evidence", []) + [s.get("evidence") for s in unit["stages"]]:
            if ref:
                existing = refs.get((ref["container"], ref["member"]))
                if existing is not None and existing != ref:
                    raise ValueError("One original member has conflicting provenance hashes.")
                refs[(ref["container"], ref["member"])] = ref
    containers, handles = {}, {}
    try:
        for (container, member), ref in refs.items():
            path = Path(container)
            _sha(ref["sha256"])
            if ref.get("container_sha256"):
                expected = _sha(ref["container_sha256"])
                if container not in containers:
                    containers[container] = hashlib.sha256(path.read_bytes()).hexdigest()
                if containers[container] != expected:
                    raise ValueError("Original evidence archive hash changed: " + container)
            if zipfile.is_zipfile(path):
                if container not in handles:
                    handles[container] = zipfile.ZipFile(path)
                raw = handles[container].read(member)
            else:
                target = (path / member).resolve() if path.is_dir() else path.resolve()
                if path.is_dir() and not target.is_relative_to(path.resolve()):
                    raise ValueError("Original evidence member escapes its source directory.")
                raw = target.read_bytes()
            if hashlib.sha256(raw).hexdigest() != ref["sha256"]:
                raise ValueError("Original evidence member hash changed: " + member)
    finally:
        for handle in handles.values():
            handle.close()
    return {"member_count": len(refs), "archive_count": len(containers), "verified": True}


def _units(bundle):
    if bundle.get("schema") != "pushpilot.delivery-first-candidate-selection.v1":
        raise ValueError("Use the explicit private delivery candidate bundle.")
    rows = list(bundle.get("shared_C_D_prefix", [])) + list(bundle.get("shared_after_green_north", []))
    rows += [u for values in bundle["branches"].values() for u in values]
    result = {}
    for unit in rows:
        if unit["id"] in result and result[unit["id"]] != unit:
            raise ValueError("Conflicting candidate IDs cannot share a route.")
        result[unit["id"]] = deepcopy(unit)
    if set(bundle["route_recipe_ids"]) != set(DESTINATIONS):
        raise ValueError("Include all three requested destinations B, C and D.")
    return result


def posture_binding_template(bundle, *, fixed_z, east, north, west=None):
    """Propose literal families; callers must review the resulting binding.

    No Euler wrapping is used. The 0.1 bound is the existing source tolerance,
    not permission to make a new physical posture or change working height.
    """
    derived_west = west is None
    if derived_west:
        west = local_wrist_pose([0.,0.,fixed_z,*north],-89.999)[3:]
    families = {"EAST": list(east), "NORTH": list(north), "WEST": list(west)}
    for name, angles in families.items():
        _pose([0, 0, fixed_z, *angles])
    mapping = {}
    for unit in _units(bundle).values():
        for stage in unit["stages"]:
            for key in ("start_base", "target_base"):
                posture = _pose(stage[key])[2:]
                candidates = [name for name, angles in families.items()
                              if _near(posture[1:], angles, .1)]
                if len(candidates) != 1 or abs(posture[0]-fixed_z) > .1:
                    raise ValueError("Original posture has no unique bounded literal family.")
                mapping[content_hash(posture)] = {"original": posture,
                    "target": [fixed_z, *families[candidates[0]]], "family": candidates[0]}
    return {"schema": "pushpilot.explicit-delivery-posture-binding.v1",
            "fixed_z": fixed_z, "families": families, "mapping": mapping,
            "west_basis": "derived_from_current_north_local_wrist_minus_89.999" if derived_west else "explicit_caller_binding",
            "west_measured_here": False,
            "review_status": "pending", "physical_qualification_created": False}


def _bounded_contacts(stages):
    """Resubdivide only an identical straight forward contact line, preserving originals."""
    indices = [i for i,s in enumerate(stages) if s["phase"] == "contact"]
    if len(indices) <= 2:
        return stages
    if indices != list(range(indices[0],indices[-1]+1)):
        raise ValueError("Contact segments cannot be merged across an intervening phase.")
    originals = stages[indices[0]:indices[-1]+1]
    start,end = originals[0]["start_base"],originals[-1]["target_base"]
    total = sum(math.dist(s["start_base"][:2],s["target_base"][:2]) for s in originals)
    direct = math.dist(start[:2],end[:2])
    if total > 40+1e-9 or abs(total-direct) > 1e-8:
        raise ValueError("More than two contacts require one <=40 mm collinear forward line.")
    line = [end[i]-start[i] for i in range(2)]
    for a,b in zip(originals,originals[1:]):
        if a["target_base"] != b["start_base"]:
            raise ValueError("Original contacts are not exactly continuous.")
    for s in originals:
        delta = [s["target_base"][i]-s["start_base"][i] for i in range(2)]
        if (s["start_base"][2:] != start[2:] or s["target_base"][2:] != start[2:]
                or abs(line[0]*delta[1]-line[1]*delta[0]) > 1e-6
                or sum(a*b for a,b in zip(line,delta)) <= 0):
            raise ValueError("Only unchanged fixed-pose collinear forward contacts can be resubdivided.")
    result,prior = [],start
    for index,target in enumerate(split_fixed_pose_tcp_segment(start,end,20.)):
        result.append({"id":"derived-contact-"+str(index+1),"phase":"contact",
            "start_base":prior,"target_base":list(target),"original_request_id":None,"evidence":None,
            "derivation":"collinear_contact_resubdivision",
            "supporting_original_stages":deepcopy(originals)})
        prior = list(target)
    return stages[:indices[0]]+result+stages[indices[-1]+1:]


def _bound_pose(pose, binding):
    pose = _pose(pose)
    if binding is None:
        return pose
    if binding.get("schema") != "pushpilot.explicit-delivery-posture-binding.v1":
        raise ValueError("Use an explicit literal posture binding, never implicit wrapping.")
    row = binding["mapping"].get(content_hash(pose[2:]))
    if not row or row["original"] != pose[2:]:
        raise ValueError("Every original posture must be explicitly represented in the binding.")
    target = _pose([*pose[:2], *row["target"]])
    if target[2] != binding["fixed_z"] or not _near(pose[2:], target[2:], .1):
        raise ValueError("Posture rebinding exceeded the original source tolerance.")
    return target


def compile_delivery_packet(bundle, source_sha256, *, posture_binding=None):
    """Return concrete geometry with separate experiment and qualification truth."""
    _sha(source_sha256)
    units = _units(bundle)
    packet = {"schema": "pushpilot.current-site-delivery-packet.v1",
        "source_bundle_sha256": source_sha256, "repeatability_qualified": False,
        "physical_qualification_created": False, "activation_enabled": False,
        "admission_mode": "site_trial", "posture_binding": deepcopy(posture_binding),
        "posture_binding_sha256": content_hash(posture_binding) if posture_binding else None,
        "contexts": {}, "primitives": {}, "routes": {}, "source_joins": [],
        "blockers": ["CURRENT_SITE_REVIEW_REQUIRED", "CURRENT_PROFILE_FULL_PATH_COVERAGE_REQUIRED",
                     "FRESH_NATIVE_AND_CURRENT_WRIST_KINEMATICS_REQUIRED",
                     "MUSE_CAR_STATE_PRECONDITIONS_AND_SIGNAL_TARGET_REQUIRED"],
        "excluded_from_blind_replay": deepcopy(bundle.get("excluded_from_blind_replay", []))}
    if posture_binding is None:
        packet["blockers"].append("EXPLICIT_FIXED_Z_POSTURE_BINDING_REQUIRED")
    numerical_vertices = []

    def canonical_vertex(pose):
        # The original source is retained separately. This explicit operation
        # joins only binary/decimal representation differences, never a pose
        # tolerance or a physical geometric gap.
        for first in numerical_vertices:
            if _near(first,pose,1e-9):
                if first != pose:
                    return list(first), {"from":list(pose),"to":list(first),
                        "maximum_component_difference":max(abs(a-b) for a,b in zip(first,pose)),
                        "bound":1e-9,"basis":"first_literal_shared_vertex"}
                return list(first), None
        numerical_vertices.append(list(pose))
        return list(pose), None

    def context(pose, tool_clear):
        for cid, row in packet["contexts"].items():
            if row["pose_base"] == pose:
                # Clearance belongs to the route state, not merely an XY match.
                if row["tool_clear"] == tool_clear:
                    return cid
        cid = "ctx-" + content_hash({"pose": pose, "tool_clear": tool_clear})[:24]
        packet["contexts"][cid] = {"pose_base": pose, "tool_clear": tool_clear,
            "clearance_basis": "current_site_review_required" if tool_clear else "contact_or_approach"}
        return cid

    def primitive(unit, *, pid=None, stages=None, source_clear=None, target_clear=None):
        pid = pid or unit["id"]
        if pid in packet["primitives"]:
            return packet["primitives"][pid]
        original_stages = _bounded_contacts(stages if stages is not None else unit["stages"])
        compiled = []
        for index, stage in enumerate(original_stages):
            phase = stage["phase"]
            if phase not in PHASES:
                raise ValueError("Every selected stage needs an explicit physical phase.")
            original_start, original_end = _pose(stage["start_base"]), _pose(stage["target_base"])
            if unit.get("posture_already_bound"):
                if stage.get("evidence") or stage.get("original_request_id"):
                    raise ValueError("Only new generated stages can already use the explicit bound posture.")
                start, end = original_start, original_end
            else:
                start, end = _bound_pose(original_start, posture_binding), _bound_pose(original_end, posture_binding)
            start,start_normalization = canonical_vertex(start)
            end,end_normalization = canonical_vertex(end)
            if phase == "wrist":
                if not _near(start[:3], end[:3]) or start[3:] == end[3:]:
                    raise ValueError("An unloaded wrist edge must retain its Cartesian anchor.")
            elif (start[2:] != end[2:] or not 0 < math.dist(start[:2], end[:2]) <= 20 + 1e-9):
                raise ValueError("Translations retain literal Z/Euler and remain at most 20 mm.")
            if compiled and not _near(compiled[-1]["target_base"], start):
                raise ValueError("A selected unit has an unreviewed internal geometry discontinuity.")
            evidence = deepcopy(stage.get("evidence"))
            if evidence:
                _sha(evidence["sha256"])
                if not stage.get("original_request_id"):
                    raise ValueError("Original receipt provenance needs its original request identity.")
            elif stage.get("original_request_id"):
                raise ValueError("A new geometry stage cannot claim an original request without evidence.")
            changed = original_start != start or original_end != end
            compiled.append({"id": stage["id"], "phase": phase,
                "start_base": start, "target_base": end,
                "geometry_basis": "derived_posture_binding" if changed else
                    ("original_completed" if evidence else "current_site_candidate"),
                "derivation": stage.get("derivation"),
                "numerical_shared_vertex_normalization":{
                    k:v for k,v in (("start",start_normalization),("target",end_normalization)) if v is not None},
                "original": {"request_id": stage.get("original_request_id"), "evidence": evidence,
                             "start_base": original_start, "target_base": original_end,
                             "supporting_segments": deepcopy(stage.get("supporting_original_stages",[]))}})
        if not compiled:
            raise ValueError("A primitive cannot contain an empty stage list.")
        wrist = any(s["phase"] == "wrist" for s in compiled)
        if wrist and (len(compiled) != 1 or compiled[0]["phase"] != "wrist"):
            raise ValueError("Keep unloaded wrist edges distinct from translations.")
        contact = sum(math.dist(s["start_base"][:2], s["target_base"][:2])
                      for s in compiled if s["phase"] == "contact")
        limit = unit.get("contact_travel_limit_mm", 40 if contact > 20 else 20)
        if not 0 < limit <= 40 or contact > limit + 1e-9:
            raise ValueError("A contact unit must retain its explicit <=40 mm total bound.")
        empty = contact == 0
        source_clear = (compiled[0]["phase"] != "contact") if source_clear is None else source_clear
        target_clear = (compiled[-1]["phase"] in {"withdraw", "empty", "wrist"}) if target_clear is None else target_clear
        row = {"id": pid, "kind": "wrist_edge" if wrist else ("coordinate_unit" if contact else "empty_path"),
            "source_context_id": context(compiled[0]["start_base"], source_clear),
            "target_context_id": context(compiled[-1]["target_base"], target_clear),
            "stages": compiled, "empty_tool": empty, "review_after": bool(unit.get("review_after")),
            "contact_travel_mm": contact, "contact_travel_limit_mm": limit,
            "expected_visual": unit.get("original_expected_visual") or
                ("The car must remain unchanged during this unloaded move." if empty else
                 "Confirm actual car progress in the intended road corridor; stop on unsupported or uncertain outcome."),
            "original_verdict": unit.get("original_verdict"),
            "original_provider_reviews": deepcopy(unit.get("original_provider_reviews", [])),
            "source_evidence": deepcopy(unit.get("source_evidence", [])),
            "source_unit_sha256": content_hash(unit),
            "candidate_reason": unit.get("reason"),
            "current_state_review_required": deepcopy(unit.get("current_state_review_required")),
            "current_site_review_required": True, "repeatability_qualified": False,
            "source_tool_clear": source_clear, "target_tool_clear": target_clear,
            "car_precondition_required": bool(contact or compiled[-1]["phase"] == "approach"),
            "clearance_precondition_required": empty,
            "runtime_source_tolerance": .1,
            "fresh_command_ids_required": True}
        if wrist:
            families = posture_binding["families"] if posture_binding else {}
            a_family = next((name for name,angles in families.items() if _near(compiled[0]["start_base"][3:],angles)),None)
            b_family = next((name for name,angles in families.items() if _near(compiled[0]["target_base"][3:],angles)),None)
            sequence = {"EAST":0,"NORTH":1,"WEST":2}
            delta = ((sequence[b_family]-sequence[a_family])*-89.999
                     if a_family in sequence and b_family in sequence else None)
            if delta is not None and not 0 < abs(delta) <= 90:
                raise ValueError("Split unloaded orientation restoration into directed <=90 degree wrist edges.")
            row["wrist"] = {"motion_mode": "directed_unloaded_current_native",
                "current_joint_source_and_target_ik_required": True,
                "historical_joints_are_commands": False,
                "source_family":a_family,"target_family":b_family,"requested_delta_j6_deg":delta,
                "literal_euler_delta_deg": [b-a for a,b in zip(compiled[0]["start_base"][3:], compiled[0]["target_base"][3:])]}
        row["geometry_sha256"] = content_hash({"kind":row["kind"], "stages":[
            {k:s[k] for k in ("phase","start_base","target_base")} for s in compiled],
            "contact_travel_limit_mm":limit})
        packet["primitives"][pid] = row
        return row

    def continuity(a, b, label):
        start = packet["contexts"][a]["pose_base"]
        end = packet["contexts"][b]["pose_base"]
        if not _near(start, end):
            packet["source_joins"].append({"label":label,"from_context":a,"to_context":b,
                "difference":[y-x for x,y in zip(start,end)],"connector_created":False})
            if not _near(start, end, .1):
                raise ValueError("Selected route has a source gap exceeding 0.1: " + label)
            if "EXPLICIT_FIXED_Z_POSTURE_BINDING_REQUIRED" not in packet["blockers"]:
                packet["blockers"].append("UNRESOLVED_LITERAL_SOURCE_CONTEXT_JOIN")
        if packet["contexts"][a]["tool_clear"] != packet["contexts"][b]["tool_clear"]:
            raise ValueError("A route join cannot silently change contact/clearance state: " + label)

    for code, ids in bundle["route_recipe_ids"].items():
        route = {"destination":DESTINATIONS[code],"steps":[],"empty_return":[],
            "parking":{"heading_deg":0.,"tolerance_deg":15.,"parallel_axis":True,"mode":"delivery_only"},
            "signal_gate_ids":[],"early_arrival_returns":{},"blockers":[]}
        previous_context = None
        pending_gate = None
        nominal_heading = 0.
        for ordinal, uid in enumerate(ids):
            unit = units[uid]
            stages = unit["stages"]
            if pending_gate:
                contact_index = next((i for i,s in enumerate(stages) if s["phase"] == "contact"), None)
                if contact_index is None or not contact_index or any(s["phase"] != "approach" for s in stages[:contact_index]):
                    raise ValueError("GREEN continuation requires an explicit measured approach to last contact.")
                recontact = primitive(unit,pid=uid+"/signal-recontact",stages=stages[:contact_index],
                                      source_clear=True,target_clear=False)
                release = packet["primitives"][pending_gate["release_to_wait_primitive_id"]]
                continuity(pending_gate["right_wait_context_id"],recontact["source_context_id"],"signal-wait-to-recontact")
                continuity(pending_gate["last_contact_context_id"],recontact["target_context_id"],"signal-last-contact")
                pending_gate["recontact_primitive_id"] = recontact["id"]
                pending_gate["entry_recheck_required"] = True
                pending_gate["seating_replay_allowed"] = False
                previous_context = recontact["target_context_id"]
                stages = stages[contact_index:]
                pid = uid+"/after-signal-recontact"
                pending_gate = None
            else:
                pid = uid
            # A leading clear traverse is a separate unloaded action, never an
            # unsupported phase hidden inside CoordinateUnit.
            prefix_length = 0
            while prefix_length < len(stages) and stages[prefix_length]["phase"] == "empty":
                prefix_length += 1
            if prefix_length and any(s["phase"] == "contact" for s in stages):
                prefix = primitive({**unit,"original_expected_visual":"The car must remain unchanged during this unloaded clear approach.",
                    "review_after":False},pid=uid+"/unloaded-prefix",stages=stages[:prefix_length])
                if previous_context:
                    continuity(previous_context,prefix["source_context_id"],uid+"/unloaded-prefix")
                    prefix["source_context_id"] = previous_context
                if not route["steps"]:
                    route["start_context_id"] = prefix["source_context_id"]
                route["steps"].append({"id":code+"-step-"+str(ordinal+1)+"-empty",
                    "primitive_id":prefix["id"],"car_zone_id":code+"-checkpoint-"+str(ordinal+1)+"-empty",
                    "expected_heading_deg":nominal_heading,"heading_measurement_available":False,
                    "heading_basis":"declared_nominal_lane_intent_not_measured_car_yaw",
                    "numeric_heading_admission_allowed":False,"at_goal":False,
                    "fresh_muse_review_required":False,"can_accept_early_arrival":False})
                previous_context = prefix["target_context_id"]
                stages = stages[prefix_length:]
                pid += "/contact-unit"
            row = primitive(unit,pid=pid,stages=stages)
            if previous_context:
                continuity(previous_context,row["source_context_id"],uid)
                # Names can coincide for tolerant telemetry joins, while stage
                # coordinates and the recorded join remain unchanged.
                row["source_context_id"] = previous_context
            if not route["steps"]:
                route["start_context_id"] = row["source_context_id"]
            contacts = [s for s in row["stages"] if s["phase"] == "contact"]
            if contacts and posture_binding:
                families = posture_binding["families"]
                family = next((name for name, angles in families.items()
                    if _near(contacts[-1]["target_base"][3:],angles)),None)
                nominal_heading = {"EAST":0.,"NORTH":-90.,"WEST":180.}.get(family,nominal_heading)
            step = {"id":code+"-step-"+str(ordinal+1),"primitive_id":row["id"],
                "car_zone_id":code+"-checkpoint-"+str(ordinal+1),
                "expected_heading_deg":nominal_heading,"heading_measurement_available":False,
                "heading_basis":"declared_nominal_lane_intent_not_measured_car_yaw",
                "numeric_heading_admission_allowed":False,
                "at_goal":ordinal == len(ids)-1,
                "fresh_muse_review_required":bool(row["review_after"]),
                "can_accept_early_arrival":bool(row["review_after"] and row["empty_tool"] is False
                    and packet["contexts"][row["target_context_id"]]["tool_clear"])}
            if unit.get("signal_gate_after"):
                last_index = max(i for i,s in enumerate(stages) if s["phase"] == "contact")
                if not stages[last_index+1:] or any(s["phase"] != "withdraw" for s in stages[last_index+1:]):
                    raise ValueError("Signal wait must have an original post-contact withdrawal.")
                release = primitive(unit,pid=uid+"/release-to-signal-wait",stages=stages[last_index+1:],
                                    source_clear=False,target_clear=True)
                step["signal_gate"] = {"id":unit["signal_gate_after"],
                    "right_wait_context_id":row["target_context_id"],
                    "last_contact_context_id":release["source_context_id"],
                    "recontact_primitive_id":None,"release_to_wait_primitive_id":release["id"],
                    "green_valid_for_s":15.}
                route["signal_gate_ids"].append(unit["signal_gate_after"])
                pending_gate = step["signal_gate"]
            route["steps"].append(step)
            previous_context = row["target_context_id"]
        if pending_gate:
            raise ValueError("A final signal wait cannot be a completed delivery route.")

        # Prepare distinct shortest straight empty returns. They are candidates
        # requiring swept-volume/car clearance review, not road graph routes.
        start_pose = packet["contexts"][route["start_context_id"]]["pose_base"]
        for step in route["steps"]:
            if not step["can_accept_early_arrival"]:
                continue
            source = packet["primitives"][step["primitive_id"]]
            pose = packet["contexts"][source["target_context_id"]]["pose_base"]
            target = [*start_pose[:2],*pose[2:]]
            targets = split_fixed_pose_tcp_segment(pose,target,19.9)
            rid = code+"/empty-return-after/"+step["id"]
            return_stages = []
            prior = pose
            for index, point in enumerate(targets):
                return_stages.append({"id":rid+"/"+str(index+1),"phase":"empty",
                    "start_base":prior,"target_base":list(point),"original_request_id":None,"evidence":None})
                prior = list(point)
            return_ids = []
            if return_stages:
                return_row = primitive({"id":rid,"stages":return_stages,"review_after":False,"posture_already_bound":True,
                    "original_expected_visual":"Empty tool returns across the reviewed clear flat area. The delivered car must remain stationary; printed roads do not constrain this empty return."})
                return_ids.append(return_row["id"])
            if not _near(target[2:],start_pose[2:]):
                if target[2] != start_pose[2]:
                    route["blockers"].append("RETURN_TO_START_HAS_UNBOUND_Z")
                families = posture_binding["families"] if posture_binding else {}
                middle = families.get("NORTH") if _near(target[3:],families.get("WEST",[])) else None
                orientations = ([middle] if middle else [])+[start_pose[3:]]
                prior_wrist = target
                for number,angles in enumerate(orientations,1):
                    wrist_id = rid+"/restore-unloaded-start-posture-"+str(number)
                    next_wrist = [*target[:3],*angles]
                    wrist_row = primitive({"id":wrist_id,"review_after":False,"posture_already_bound":True,"stages":[{
                        "id":wrist_id,"phase":"wrist","start_base":prior_wrist,
                        "target_base":next_wrist,"original_request_id":None,"evidence":None}],
                        "original_expected_visual":"Unloaded orientation restoration at START. The delivered car must remain unchanged; fresh directed joint and clearance review are required."})
                    return_ids.append(wrist_row["id"])
                    prior_wrist = next_wrist
            if not return_ids:
                continue
            last = packet["primitives"][return_ids[-1]]
            last["target_context_id"] = route["start_context_id"]
            packet["contexts"][route["start_context_id"]]["clearance_is_state_dependent"] = True
            # START is only made ready after return; no car reset is inferred.
            route["early_arrival_returns"][step["id"]] = return_ids
        final = route["steps"][-1]["id"]
        route["empty_return"] = route["early_arrival_returns"].get(final, [])
        if not route["empty_return"]:
            route["blockers"].append("FINAL_WITHDRAWN_RETURN_SOURCE_REQUIRED")
        route["counts"] = {"route_units":len(route["steps"]),
            "route_stages":sum(len(packet["primitives"][s["primitive_id"]]["stages"]) for s in route["steps"]),
            "recontact_stages":sum(len(packet["primitives"][s["signal_gate"]["recontact_primitive_id"]]["stages"])
                for s in route["steps"] if s.get("signal_gate")),
            "return_stages":sum(len(packet["primitives"][pid]["stages"]) for pid in route["empty_return"])}
        packet["routes"][code] = route
    repair_signal_departures(packet)
    packet["geometry_manifest_sha256"] = content_hash({
        "primitives":packet["primitives"],
        "routes":packet["routes"],"contexts":packet["contexts"],
        "posture_binding_sha256":packet["posture_binding_sha256"]})
    return packet


def repair_signal_departures(packet):
    """Prepare one-departure candidates; never activate or move hardware.

    Reverse the actual withdrawal rather than borrowing the next historical
    unit's lateral approach. Reversed geometry is a candidate, not an executed
    reverse-motion receipt. Preserve the source hash for independent review.
    """
    repaired = {}
    for route in packet["routes"].values():
        for step in route["steps"]:
            gate = step.get("signal_gate")
            if not gate:
                continue
            pid = gate["recontact_primitive_id"]
            release = packet["primitives"][gate["release_to_wait_primitive_id"]]
            row = packet["primitives"][pid]
            if pid not in repaired:
                stages = []
                for index, source in enumerate(reversed(release["stages"]), 1):
                    start, end = source["target_base"], source["start_base"]
                    if (source["phase"] != "withdraw" or start[2:] != end[2:]
                            or not 0 < math.dist(start[:2], end[:2]) <= 20 + 1e-9
                            or stages and stages[-1]["target_base"] != start):
                        raise ValueError("Signal recontact needs an exact bounded fixed-pose withdrawal inverse.")
                    stages.append({"id":pid+"/inverse-withdraw-"+str(index), "phase":"approach",
                        "start_base":deepcopy(start), "target_base":deepcopy(end),
                        "geometry_basis":"current_site_candidate",
                        "derivation":{"method":"reverse_withdrawal", "source_primitive_id":release["id"],
                            "source_geometry_sha256":release["geometry_sha256"], "source_stage_id":source["id"]},
                        "original":{"request_id":None,"evidence":None,"supporting_segments":[]}})
                if (not stages or stages[0]["start_base"] != packet["contexts"][gate["right_wait_context_id"]]["pose_base"]
                        or stages[-1]["target_base"] != packet["contexts"][gate["last_contact_context_id"]]["pose_base"]):
                    raise ValueError("Signal withdrawal inverse must preserve exact WAIT and CONTACT endpoints.")
                row["superseded_approach_geometry_sha256"] = row["geometry_sha256"]
                row["superseded_approach_stages"] = deepcopy(row["stages"])
                row["stages"] = stages
                row["original_verdict"] = None
                row["repeatability_qualified"] = False
                row["candidate_reason"] = "Exact inverse of withdrawal, including final normal approach; reverse direction needs physical validation."
                row["geometry_sha256"] = content_hash({"kind":row["kind"],
                    "stages":[{k:s[k] for k in ("phase","start_base","target_base")} for s in stages],
                    "contact_travel_limit_mm":row["contact_travel_limit_mm"]})
                repaired[pid] = release["id"]
            elif repaired[pid] != release["id"]:
                raise ValueError("A shared recontact cannot reverse different withdrawals.")
            gate.update(entry_policy="single_departure", entry_recheck_required=False,
                        seating_replay_allowed=False)
        route["counts"]["recontact_stages"] = sum(len(packet["primitives"][s["signal_gate"]["recontact_primitive_id"]]["stages"])
            for s in route["steps"] if s.get("signal_gate"))


def policy_plan(packet, route_code, site_binding, review_sha256, *, plan_id):
    """Adapt an independently reviewed site trial to the policy dataclass shape.

    The review must cover this packet's manifest, site, profile, current wrist
    edges, swept clearance and vehicle preconditions. This helper validates the
    reference format only; the real driver owns review admission and freshness.
    """
    _sha(review_sha256)
    route = packet["routes"][route_code]

    def reference(pid):
        p = packet["primitives"][pid]
        return {"id":pid,"source_context_id":p["source_context_id"],
            "target_context_id":p["target_context_id"],"qualification_sha256":ZERO_SHA,
            "qualified":False,"empty_tool":p["empty_tool"],
            "release_mode":"site_trial","current_site_review_sha256":review_sha256}

    steps = []
    for row in route["steps"]:
        step = {k:row[k] for k in ("id","car_zone_id","expected_heading_deg","at_goal")}
        step["primitive"] = reference(row["primitive_id"])
        if row.get("signal_gate"):
            gate = row["signal_gate"]
            step["signal_gate"] = {k:gate[k] for k in ("id","right_wait_context_id","last_contact_context_id","green_valid_for_s")}
            step["signal_gate"].update(recontact=reference(gate["recontact_primitive_id"]),
                release_to_wait=reference(gate["release_to_wait_primitive_id"]),
                entry_policy=gate.get("entry_policy", "fresh_entry"))
        steps.append(step)
    return {"id":plan_id,"destination":route["destination"],"binding":site_binding,
        "steps":steps,"parking":route["parking"],"empty_return":[reference(p) for p in route["empty_return"]],
        "start_context_id":route["start_context_id"],"release_mode":"site_trial"}


def review_template(packet):
    return {"schema":"pushpilot.current-site-delivery-review.v1","status":"pending",
        "geometry_manifest_sha256":packet["geometry_manifest_sha256"],
        "source_bundle_sha256":packet["source_bundle_sha256"],
        "posture_binding_sha256":packet["posture_binding_sha256"],
        "installation_id":None,"current_profile_sha256":None,
        "accepted_primitive_geometry_sha256":{pid:p["geometry_sha256"] for pid,p in packet["primitives"].items()},
        "swept_clearance_evidence_sha256":None,"current_wrist_kinematics_evidence_sha256":None,
        "car_state_preconditions_evidence_sha256":None,"signal_placement_evidence_sha256":None,
        "repeatability_qualified":False,"automatic_release_created":False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle",type=Path)
    parser.add_argument("--output",required=True,type=Path)
    parser.add_argument("--posture-binding",type=Path)
    args = parser.parse_args(argv)
    raw = args.bundle.read_bytes()
    bundle = json.loads(raw)
    checked = verify_original_evidence(bundle)
    binding = json.loads(args.posture_binding.read_bytes()) if args.posture_binding else None
    packet = compile_delivery_packet(bundle,hashlib.sha256(raw).hexdigest(),posture_binding=binding)
    packet["source_evidence_verification"] = checked
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(packet,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    review = args.output.with_name(args.output.stem+".review-template.json")
    review.write_text(json.dumps(review_template(packet),indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"packet":str(args.output),"geometry_manifest_sha256":packet["geometry_manifest_sha256"],
        "routes":{k:v["counts"] for k,v in packet["routes"].items()},"physical_qualification_created":False}))


if __name__ == "__main__":
    main()
