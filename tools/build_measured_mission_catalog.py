"""Build a private candidate catalogue from hash-verified commissioning evidence.

Usage: python -m tools.build_measured_mission_catalog --audit-dir PATH --output PATH
No network, robot, camera, provider, deployment or operating-state mutations.
The output cannot be used as an armed adapter or a historical-command replay.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import zipfile

from backend.robot_control.mission_catalog import (
    EvidenceReference, MeasuredPrimitive, MeasuredStage, check_recipe_continuity,
    content_hash, deduplicate_motions, match_measured_recontact, verify_journal,
    disabled_route_template,
)


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class EvidenceStore:
    """Only selected archive members are read; ZIP paths are never extracted."""
    def __init__(self, inventories: list[dict]):
        self.sources, self.verified_members = {}, set()
        for item in inventories:
            path = Path(item["path"]).resolve()
            if path.is_file():
                if file_hash(path) != item["sha256"]:
                    raise ValueError(f"Archive checksum changed: {path.name}")
                archive = zipfile.ZipFile(path)
                if len(set(archive.namelist())) != len(archive.namelist()):
                    raise ValueError("Duplicate ZIP member paths are ambiguous.")
                self.sources[str(path)] = (archive, item["sha256"])
            else:
                self.sources[str(path)] = (None, None)

    def raw(self, container: str, member: str) -> bytes:
        path = Path(container).resolve()
        archive, _ = self.sources[str(path)]
        member_path = PurePosixPath(member)
        if member_path.is_absolute() or ".." in member_path.parts or "\\" in member:
            raise ValueError("Evidence member paths must be relative and bounded.")
        if archive is not None:
            return archive.read(member)
        target = (path / member).resolve()
        if not target.is_relative_to(path):
            raise ValueError("Loose evidence escaped its selected source.")
        return target.read_bytes()

    def read_reference(self, ref: dict) -> dict:
        archive_hash = self.sources[str(Path(ref["container"]).resolve())][1]
        if ref.get("container_sha256") != archive_hash:
            raise ValueError("A record references a different source archive.")
        raw = self.raw(ref["container"], ref["member"])
        if hashlib.sha256(raw).hexdigest() != ref["sha256"]:
            raise ValueError("Original evidence member hash changed.")
        self.verified_members.add((ref["container"], ref["member"]))
        return json.loads(raw)

    def reference(self, container: str, member: str) -> EvidenceReference:
        raw = self.raw(container, member)
        self.verified_members.add((container, member))
        return EvidenceReference(container, member, hashlib.sha256(raw).hexdigest(),
                                 self.sources[str(Path(container).resolve())][1])

    def close(self):
        for archive, _ in self.sources.values():
            if archive:
                archive.close()


def verify_motion(row: dict, store: EvidenceStore) -> None:
    job = store.read_reference(row["original_job"])
    receipt = (job.get("result") or {}).get("robot_receipt") or {}
    data, payload = receipt.get("data", {}), job.get("payload", {})
    expected = payload.get("expected_receiver", {})
    if (job.get("state") != "complete" or receipt.get("kind") != "motion_endpoint_verified"
            or data.get("physical_execution") is not True or data.get("operation") != row["kind"]
            or job.get("id") != row["request_id"] or payload.get("request_id") != row["request_id"]
            or payload.get("kind") != row["kind"] or data.get("session_id") != row["session_id"]
            or expected.get("session_id") != row["session_id"] or expected.get("seq") != data.get("seq")
            or data.get("seq", -2) + 1 != row["receiver_endpoint_sequence"]
            or data.get("previous") != row["start_base_mm_deg"]
            or data.get("target") != row["end_base_mm_deg"]
            or payload.get("target") != row["end_base_mm_deg"]):
        raise ValueError("Audited motion differs from the original command/receipt identity.")


COMMON_BLOCKERS = ("CURRENT_INSTALLATION_RELEASE_REQUIRED", "VEHICLE_PRECONDITION_ENVELOPE_UNMEASURED",
                   "AUTONOMOUS_REPEATABILITY_NOT_ESTABLISHED")


def stage_from_row(row: dict, phase: str, stage_id: str | None = None) -> MeasuredStage:
    return MeasuredStage(stage_id or row["request_id"], phase, tuple(row["start_base_mm_deg"]),
        tuple(row["end_base_mm_deg"]), row["request_id"], EvidenceReference(**row["original_job"]))


def unit_from_journal(events: list[dict], ref: EvidenceReference,
                      motions: dict[str, dict]) -> tuple[MeasuredPrimitive | None, dict]:
    inputs = [e["payload"]["unit"] for e in events if e["kind"] == "coordinate_unit_input"]
    endpoints = [e["payload"] for e in events if e["kind"] == "coordinate_stage_endpoint"]
    reviews = [e["payload"]["result"] for e in events if e["kind"] == "coordinate_unit_review"]
    if not inputs or not endpoints:
        return None, {"journal": asdict(ref), "reason": "No executed coordinate-unit endpoints.",
                      "separate_readonly_outcomes": [{"kind": e["kind"], "payload": e["payload"]}
                          for e in events if "outcome" in e["kind"] or "review" in e["kind"]],
                      "original_failure_not_overwritten": True}
    if len(inputs) != 1 or len(reviews) > 1:
        raise ValueError("Ambiguous unit input or original review in one journal.")
    unit, stages = inputs[0], []
    declared = {s["id"]: s for s in unit["stages"]}
    for endpoint in endpoints:
        intent, recorded = endpoint["intent"], endpoint["stage"]
        row = motions[intent["request_id"]]
        native = endpoint["native_after"]
        if (recorded != declared[recorded["id"]]
                or recorded["start_base"] != row["start_base_mm_deg"]
                or recorded["target_base"] != row["end_base_mm_deg"]
                or native["tcp_base"] != row["end_base_mm_deg"]
                or native["session_id"] != row["session_id"]
                or native["sequence"] != row["receiver_endpoint_sequence"]):
            raise ValueError("Recorded unit stage does not match its Native-confirmed physical command.")
        stages.append(stage_from_row(row, recorded["phase"], recorded["id"]))
    review = reviews[0] if reviews else {}
    verdict = review.get("verdict", "MISSING")
    complete = [s.id for s in stages] == [s["id"] for s in unit["stages"]]
    blockers = list(COMMON_BLOCKERS)
    if not complete:
        blockers.append("PARTIAL_EXECUTION_DO_NOT_RESUME_BY_REPLAY")
    if verdict != "PASS":
        blockers.append("ORIGINAL_OUTCOME_" + verdict)
    result = MeasuredPrimitive(unit["id"], "coordinate_unit" if complete else "partial_unit", tuple(stages),
        unit["source"], unit["target"], unit["expected_visual"], verdict, review.get("arrived", False),
        (ref,), tuple(blockers), unit.get("at_goal", False), unit.get("contact_travel_limit_mm", 20.))
    return result, {"id": result.id, "original_review": review or None,
        "complete": complete, "original_event_count": len(events),
        "interruption_events": [{"kind": e["kind"], "payload": e["payload"]} for e in events
                                if "failed" in e["kind"] or "interrupt" in e["kind"]]}


def phase_path(primitive: MeasuredPrimitive, phase: str) -> MeasuredPrimitive | None:
    stages = tuple(s for s in primitive.stages if s.phase == phase)
    if not stages:
        return None
    return MeasuredPrimitive(primitive.id + ":" + phase,
        "recontact_path" if phase == "approach" else "observation_path", stages,
        primitive.source, primitive.target, primitive.expected_visual,
        primitive.original_verdict, False, primitive.evidence,
        primitive.blockers + ("WHOLE_UNIT_OUTCOME_NOT_ISOLATED_PHASE_QUALIFICATION",))


def _supplemental_rows(audit_dir: Path) -> tuple[list[dict], list[dict]]:
    """Include recovered originals omitted by the first archive-selection cutoffs."""
    rows, sources = [], []
    expanded = audit_dir / "C-expanded-original-lineage.private.json"
    if expanded.exists():
        value = json.loads(expanded.read_bytes())
        rows.extend(value["ordered_C_motions"])
        sources.append({"path": str(expanded), "sha256": file_hash(expanded),
                        "scope": "Original C lineage including early archive and NORTH3"})
    north = audit_dir / "C-NORTH3-originals/remote-manifest.private.json"
    if north.exists():
        manifest = json.loads(north.read_text(encoding="utf-8-sig"))
        for item in manifest["files"]:
            path = (north.parent / item["path"]).resolve()
            if not path.is_relative_to(north.parent.resolve()):
                raise ValueError("Copied evidence escaped the manifest directory.")
            if path.stat().st_size != item["bytes"] or file_hash(path) != item["sha256"]:
                raise ValueError("A recovered NORTH3 original differs from its remote checksum.")
        sources.append({"path": str(north), "sha256": file_hash(north), "verified_files": len(manifest["files"])})
    returned = audit_dir / "empty-return-20261028T172500927318Z"
    if returned.exists():
        for path in sorted(returned.glob("*.result.private.json")):
            job = json.loads(path.read_bytes())
            data = ((job.get("result") or {}).get("robot_receipt") or {}).get("data", {})
            if job.get("state") != "complete" or data.get("operation") != "translate":
                continue
            payload = job["payload"]
            rows.append({"family": "B", "phase": "empty", "request_id": job["id"],
                "session_id": data["session_id"], "receiver_endpoint_sequence": data["seq"]+1,
                "kind": "translate", "start_base_mm_deg": data["previous"], "end_base_mm_deg": data["target"],
                "expected_visual": payload["expected_visual"],
                "translation_distance_mm": math.dist(data["previous"][:3], data["target"][:3]),
                "original_job": {"container": str(returned.resolve()), "member": path.name,
                    "sha256": file_hash(path), "container_sha256": None}})
        sources.append({"path": str(returned), "scope": "Eleven original completed B empty return commands"})
    return rows, sources


def _historical_routes(rows, store, primitives, empty_paths, wrists, signal):
    """Preserve complete delivered histories independently of autonomous release.

    Unclassified old strokes remain explicit unclassified candidates. A supplied
    driver template contains every original coordinate, yet has no executable
    policy/release until each car-state transition and observation is qualified.
    """
    by_motion = {}
    for primitive in primitives.values():
        for stage in primitive.stages:
            by_motion[stage.original_request_id] = (primitive, stage)
    measured = dict(primitives)
    for p in empty_paths:
        measured[p.id] = p
    from backend.robot_control.mission_catalog import primitive_from_dict
    for p in wrists:
        measured[p["id"]] = primitive_from_dict(p)
    jobs = {r["request_id"]: store.read_reference(r["original_job"]) for r in rows}
    chronological = sorted(rows, key=lambda r: (jobs[r["request_id"]]["created"], r["request_id"]))
    history, templates, lineages = [], {}, {}
    recovery = _recovery_link(store)

    def stage_primitive(row):
        if row["kind"] == "rotate":
            return measured["wrist:" + row["request_id"]]
        parent, stage = by_motion.get(row["request_id"], (None, None))
        phase = stage.phase if stage else row.get("phase", "unclassified")
        p = MeasuredPrimitive("history:" + row["request_id"],
            "empty_path" if phase == "empty" else "partial_unit",
            (stage_from_row(row, phase),), row["family"] + "_HISTORICAL_SOURCE",
            row["family"] + "_HISTORICAL_TARGET", row.get("expected_visual") or "Original measured robot stage.",
            parent.original_verdict if parent else "MISSING", False,
            (EvidenceReference(**row["original_job"]),),
            COMMON_BLOCKERS + ("ORIGINAL_STAGE_IS_NOT_AN_ISOLATED_CAR_RESPONSE_QUALIFICATION",))
        if p.id not in measured:
            measured[p.id] = p
            history.append(p.to_dict())
        return p

    for family, destination in (("B", "OFFICE_BUILDING"), ("C", "VILLA"), ("D", "HANOK")):
        selected = [r for r in chronological if r["family"] == family]
        if family == "D":
            # The operator reset the car once after endpoint333. Do not stitch
            # earlier failed central trials across that physical car reset.
            selected = [r for r in selected if r["receiver_endpoint_sequence"] > 333]
        route, returning, route_rows, return_rows = [], [], [], []
        prior = None
        for row in selected:
            is_return = family == "B" and row.get("phase") == "empty" or family == "C" and (
                row["receiver_endpoint_sequence"] > 180
                and row["session_id"] == "bbc5d84d87ee4246afc64003fef1d5e6")
            p = stage_primitive(row)
            target = returning if is_return else route
            if family == "C" and prior and prior["end_base_mm_deg"] != row["start_base_mm_deg"]:
                if recovery is None:
                    target.append({"gap": {"id": "C_ORIGINAL_RECOVERY_EVIDENCE_REQUIRED",
                                           "reason": "Original interrupted move reconciliation was not included."}})
                else:
                    if (prior["end_base_mm_deg"] != recovery["source_base"]
                            or row["start_base_mm_deg"] != recovery["fresh_receiver_base"]):
                        raise ValueError("C recovery evidence does not close the original source lineage.")
                    target.append({"historical_reconciliation": recovery})
            target.append({"role": "empty_return" if is_return else "original_delivery_stage", "primitive_ids": [p.id]})
            (return_rows if is_return else route_rows).append(row)
            prior = row
        arrival = {"historical_vehicle_delivered": True, "source":
            "operator_acceptance" if family == "C" else "original_MUSE_arrival", "autonomous_repeatability": False}
        if family == "C":
            container = next(c for c in store.sources if "C-operator-accepted" in c)
            ref = store.reference(container, "C-operator-arrival-20261028T234612926760Z/operator-acceptance.private.json")
            arrival.update(reference=asdict(ref), original=json.loads(store.raw(container, ref.member)))
        gaps = []
        if not returning:
            returning = [{"gap": {"id": family+"_RETURN_FROM_ACTUAL_FINAL_OBSERVATION",
                "reason": "No selected original empty return begins at this destination's final observation. Delivery itself is evidenced."}}]
        if family == "C":
            gaps.append({"id": "C_SIGNAL_WAIT_INSTALLATION_IN_ORIGINAL_LINEAGE",
                "reason": "Original complete C delivery is retained. The newer D-selected RIGHT signal park cannot be inserted into this older C car state without a qualified transition."})
        arrival["original_final_robot_endpoint"] = route_rows[-1]["end_base_mm_deg"]
        templates[destination] = disabled_route_template(destination, route, returning, measured,
            signal_plan={"selected_right_wait": signal["id"], "configured_and_qualified": False,
                         "applicability": "requires route-specific measured entry/stop binding"},
            arrival_evidence=arrival, additional_gaps=gaps)
        lineages[family] = {"destination": destination, "historical_delivery": arrival,
            "completed_delivery_motion_count": len(route_rows), "completed_empty_return_motion_count": len(return_rows),
            "source_start_base": route_rows[0]["start_base_mm_deg"],
            "ordered_original_motion_references": [r["original_job"] for r in selected],
            "reconciled_interrupted_motion": recovery if family == "C" else None,
            "return_end_base": return_rows[-1]["end_base_mm_deg"] if return_rows else None,
            "literal_return_matches_original_start": return_rows[-1]["end_base_mm_deg"] == route_rows[0]["start_base_mm_deg"] if return_rows else None,
            "return_XY_matches_original_start_within_1e_9_mm": math.dist(return_rows[-1]["end_base_mm_deg"][:2], route_rows[0]["start_base_mm_deg"][:2]) <= 1e-9 if return_rows else None,
            "literal_return_minus_original_start": [b-a for a,b in zip(route_rows[0]["start_base_mm_deg"], return_rows[-1]["end_base_mm_deg"])] if return_rows else None,
            "operator_or_recovery_interventions_preserved": True, "autonomous_replay_qualified": False}
    return history, templates, lineages


def _recovery_link(store):
    container = next((c for c in store.sources if "C-coordinate-units-through2" in c), None)
    original_container = next((c for c in store.sources if "C-unknown181" in c), None)
    if container is None or original_container is None:
        return None
    prefix = "C-original-receiver-recovery-20261028T211448767448Z/reconciliation-attempt-2/"
    evidence = json.loads(store.raw(container, prefix+"reconciliation-evidence.private.json"))
    result = json.loads(store.raw(container, prefix+"reconciliation-result.private.json"))
    original_name = "incident/C-next-front-follow-RETURN-REAR-1-20261028T205142763313Z/result.private.json"
    original = json.loads(store.raw(original_container, original_name))
    before_name = "incident/C-next-front-follow-RETURN-REAR-1-20261028T205142763313Z/before.status.private.json"
    before = json.loads(store.raw(original_container, before_name))
    proof_name = prefix + evidence["new_stationary_proof"]
    proof = store.reference(container, proof_name)
    if (result["state"] != "reconciled" or result["error"] != "confirmed_completed"
            or result["id"] != original["id"] or result["payload"] != original["payload"]
            or proof.sha256 != evidence["proof_sha256"] or evidence["original_done_missing"] is not True
            or evidence["new_command_issued"] is not False):
        raise ValueError("C recovery must preserve the original unknown result and fresh confirmation.")
    return {"id": "C_CONFIRMED_COMPLETED_WITH_ORIGINAL_DONE_MISSING", "original_request_id": result["id"],
        "source_base": before["receiver"]["actual_pose"], "original_target_base": evidence["original_target"],
        "fresh_receiver_base": evidence["new_actual_tcp"], "literal_native_residual": evidence["literal_residual"],
        "original_done_missing": True, "new_command_issued": False, "automatically_executable": False,
        "evidence": [asdict(store.reference(original_container, original_name)),
                     asdict(store.reference(container, prefix+"reconciliation-result.private.json")),
                     asdict(store.reference(container, prefix+"reconciliation-evidence.private.json")), asdict(proof)],
        "release_blocker": "RECONCILED_ORIGINAL_EDGE_AND_NEW_NATIVE_BASELINE_NEED_CURRENT_RELEASE"}


def build_catalogue(audit_dir: Path) -> dict:
    audit = json.loads((audit_dir / "analysis.private.json").read_bytes())
    original_rows = json.loads((audit_dir / "motions.private.json").read_bytes())
    supplemental, supplemental_sources = _supplemental_rows(audit_dir)
    rows, duplicates = deduplicate_motions(original_rows + supplemental)
    inventories = list(audit["selected_source_inventories"])
    known = {str(Path(i["path"]).resolve()) for i in inventories}
    for row in rows:
        ref = row["original_job"]
        path = str(Path(ref["container"]).resolve())
        if path not in known:
            inventories.append({"path": path, "sha256": ref["container_sha256"]})
            known.add(path)
    # Recovery records are evidence links, not fabricated successful commands.
    unknown = audit_dir.parent / "C-unknown181/originals.private.zip"
    if unknown.exists() and str(unknown.resolve()) not in known:
        inventories.append({"path": str(unknown.resolve()), "sha256": file_hash(unknown)})
    store = EvidenceStore(inventories)
    try:
        for row in rows:
            verify_motion(row, store)
        motions = {r["request_id"]: r for r in rows}
        primitives, histories, skipped, journals = {}, {}, [], {}
        for container, (archive, _) in store.sources.items():
            if archive is None:
                continue
            for member in archive.namelist():
                if not member.endswith("/events.private.jsonl"):
                    continue
                raw = store.raw(container, member)
                digest = hashlib.sha256(raw).hexdigest()
                if digest in journals:
                    continue
                events = verify_journal(raw)
                ref = store.reference(container, member)
                journals[digest] = ref
                primitive, history = unit_from_journal(events, ref, motions)
                if primitive is None:
                    skipped.append(history)
                    continue
                if primitive.id in primitives:
                    raise ValueError("Distinct event journals conflict on a primitive ID.")
                primitives[primitive.id] = primitive
                histories[primitive.id] = history
        # B is the legacy continuous contact course, not a fabricated new unit.
        b_rows = sorted((r for r in rows if r["family"] == "B" and r.get("phase") != "empty"),
                        key=lambda r:r["receiver_endpoint_sequence"])
        b_container = b_rows[0]["original_job"]["container"]
        b_ref = store.reference(b_container, "B-course.summary.private.json")
        b_summary = json.loads(store.raw(b_container, b_ref.member))
        if (len(b_rows) != b_summary["contact_strokes"] or b_summary["vehicle_arrival"]["status"] != "ARRIVED"
                or b_summary["vehicle_arrival_source"] != "meta_original_live_pair"):
            raise ValueError("Original B arrival/contact summary does not match the audited strokes.")
        b = MeasuredPrimitive("B-original-contact-course", "contact_strokes",
            tuple(stage_from_row(r, "contact") for r in b_rows), "PIZZA", "OFFICE_BUILDING",
            "Original twelve contact strokes ended with a separate MUSE vehicle-arrival observation.",
            "ARRIVED", True, (b_ref,), COMMON_BLOCKERS,
            True, sum(r["translation_distance_mm"] for r in b_rows))
        primitives[b.id] = b
        phase_paths = [p for primitive in primitives.values() for phase in ("approach", "withdraw")
                       if (p := phase_path(primitive, phase)) is not None]
        # Preserve directed unloaded wrist edges and their exact original joint pair.
        wrists, empty_rows = [], []
        for row in rows:
            text = re.sub(r"\s+", "", row.get("expected_visual") or "").lower()
            if row["kind"] == "rotate":
                primitive = MeasuredPrimitive("wrist:" + row["request_id"], "wrist_edge",
                    (stage_from_row(row, "wrist"),), "MEASURED_UNLOADED_ANCHOR", "MEASURED_UNLOADED_ANCHOR",
                    row["expected_visual"], "MISSING", False, (EvidenceReference(**row["original_job"]),),
                    ("CURRENT_INSTALLATION_RELEASE_REQUIRED", "EXACT_DIRECTED_JOINT_SOURCE_REQUIRED",
                     "CURRENT_FK_PREFLIGHT_REQUIRED", "NO_VEHICLE_TURN_INFERRED"))
                wrists.append({**primitive.to_dict(), "measured_rotation_edge": row["measured_rotation_edge"],
                    "rotation_runtime": row["rotation_runtime"], "original_joint_after": row["after_joint_deg"],
                    "original_joint_before": row["before_joint_deg"]})
            elif row.get("phase") == "empty" or row.get("phase") == "unclassified" and "emptytool" in text:
                empty_rows.append(row)
        # Group only original consecutive same-session, exactly contiguous empty motions.
        empty_paths, group = [], []
        empty_ids = {r["request_id"] for r in empty_rows}
        for row in sorted(rows, key=lambda r:(r["session_id"], r["receiver_endpoint_sequence"])):
            if row["request_id"] not in empty_ids:
                if group:
                    empty_paths.append(_empty_path(group))
                    group = []
                continue
            if group and (group[-1]["session_id"] != row["session_id"]
                    or group[-1]["end_base_mm_deg"] != row["start_base_mm_deg"]):
                empty_paths.append(_empty_path(group))
                group = []
            group.append(row)
        if group:
            empty_paths.append(_empty_path(group))
        signal = _signal_catalogue(store, primitives, phase_paths)
        selected = _selected_recipes(primitives, empty_paths, wrists)
        d_final = primitives["D-fixed-plan-review-20261029T055617515443Z"]
        last_contact, obs = d_final.last_contact_base, d_final.observation_base
        histories_catalogue, route_templates, lineage = _historical_routes(
            rows, store, primitives, empty_paths, wrists, signal)
        d_return_report = audit_dir / "D-final-empty-corridor-search.private.json"
        if d_return_report.exists():
            route_templates["HANOK"]["derived_empty_return_candidate"] = {
                "report": str(d_return_report), "sha256": file_hash(d_return_report),
                "status": "derived_candidate_not_executed_or_qualified",
                "description": "Seventeen-stage corridor candidate uses existing coordinates and one proposed reverse 10 mm FREE-ROW transition. It is not an executed complete return or admitted primitive.",
                "automatically_executable": False}
        return {"schema": "pushpilot.measured-mission-catalogue.v1", "mode": "candidate_geometry_only",
            "source_audit_sha256": file_hash(audit_dir / "analysis.private.json"),
            "source_motion_registry_sha256": file_hash(audit_dir / "motions.private.json"),
            "supplemental_sources": supplemental_sources,
            "counts": {"actual_motions_verified": len(rows), "duplicate_motion_rows_removed": duplicates,
                       "unique_journals_verified": len(journals), "primitives": len(primitives),
                       "phase_paths": len(phase_paths), "directed_wrist_edges": len(wrists),
                       "empty_paths": len(empty_paths), "original_members_verified": len(store.verified_members),
                       "historical_stage_candidates": len(histories_catalogue),
                       "original_unit_verdicts": dict(Counter(p.original_verdict for p in primitives.values()))},
            "primitives": [p.to_dict() for p in primitives.values()] + histories_catalogue,
            "phase_paths": [p.to_dict() for p in phase_paths],
            "unloaded_wrist_edges": wrists, "empty_paths": [p.to_dict() for p in empty_paths],
            "original_outcomes_and_interruptions": list(histories.values()), "skipped_journals": skipped,
            "selected_recipes": selected, "signal_wait": signal,
            "historical_delivery_lineages": lineage, "disabled_route_templates": route_templates,
            "destination_D": {"actual_arrival_primitive": d_final.id, "last_contact_base": last_contact,
                "observation_base": obs, "contact_to_observation_mm": math.dist(last_contact[:3], obs[:3]),
                "metric_parking_heading_error_deg": None,
                "return_path_starts_at_final_observation": [p.id for p in empty_paths if p.stages[0].start_base == obs]},
            "safety_semantics": {"hardware_calls": 0, "network_calls": 0, "automatic_motion_authority_created": False,
                "historical_session_profile_mailbox_replay": False, "metric_car_response_model_created": False,
                "full_map_to_base_fit_accepted": False, "missing_preconditions_filled_by_inference": False}}
    finally:
        store.close()


def _empty_path(rows: list[dict]) -> MeasuredPrimitive:
    return MeasuredPrimitive("empty:" + rows[0]["request_id"], "empty_path",
        tuple(stage_from_row(r, "empty") for r in rows), "MEASURED_EMPTY_SOURCE", "MEASURED_EMPTY_TARGET",
        rows[0]["expected_visual"], "MISSING", False,
        tuple(EvidenceReference(**r["original_job"]) for r in rows),
        ("CURRENT_INSTALLATION_RELEASE_REQUIRED", "CURRENT_CAR_EXCLUSION_REQUIRED",
         "EXACT_SOURCE_AND_POSTURE_REQUIRED", "NO_REVERSED_PATH_INFERRED"))


def _signal_catalogue(store, primitives, phase_paths):
    container = next(c for c in store.sources if "D-Hanok-arrival-cutoff637" in c)
    member = "D-operator-signal-wait-selection-20261029T042244760501Z/signal-wait-stage.private.json"
    selection = json.loads(store.raw(container, member))
    ref = store.reference(container, member)
    seat = primitives["D-fixed-plan-review-20261029T041620314128Z"]
    observation, contact = seat.observation_base, seat.last_contact_base
    if (list(observation) != selection["robot_observation_wait_pose"]["actual_tcp_base_mm_deg"]
            or list(contact) != selection["coordinate_departure_reference"]["recontact_target_base_mm_deg"]):
        raise ValueError("Selected signal park/contact differs from its actual seat unit.")
    recontact = match_measured_recontact(observation, contact, tuple(phase_paths))
    return {"id": selection["id"], "side": "RIGHT", "required_visibility": "CAR_AND_CONFIGURED_SIGNAL",
        "selection_evidence": asdict(ref), "arrival_unit_id": seat.id,
        "observation_base": observation, "last_contact_base": contact,
        "measured_recontact_path_id": recontact.id if recontact else None,
        "measured_recontact_stage_count": len(recontact.stages) if recontact else 0,
        "recontact_parent_original_verdict": recontact.original_verdict if recontact else None,
        "recontact_replays_seating": False, "recontact_reversed_from_withdrawal": False,
        "physical_signal_target_configured": selection["physical_signal_target_configured"],
        "signal_face_readable_in_original": selection["view_evidence"]["result"]["actual_signal_face_readable"],
        "blockers": ["CURRENT_SIGNAL_TARGET_AND_VIEW_BINDING_REQUIRED", "FRESH_MUSE_GREEN_REQUIRED",
                     "VERIFIED_CURRENT_STOP_REQUIRED", "QUALIFIED_CROSSING_AFTER_RECONTACT_REQUIRED"],
        "automatic_crossing_authority": False}


def _selected_recipes(primitives, empty_paths, wrists):
    prefix = "D-fixed-plan-review-20261029T"
    groups = {
        "B_OFFICE_CONTACT": ["B-original-contact-course"],
        "SHARED_C_D_START_FRONTAGE": [prefix + x + "Z" for x in
            ("034234981825", "034418293000", "034547242944", "034716442000", "034845134379", "035019375783")],
        "SHARED_C_D_FIRST_TURN": [prefix + x + "Z" for x in
            ("040356680813", "040618103199", "040822582862", "041036447126", "041620314128")],
        "C_VILLA_WEST_CONTACT": ["C-west-course-review-20261028T231958806301Z",
            "C-west-next-unit-review-20261028T232703974338Z", "C-west-next-unit-review-20261028T233142810969Z"],
        "D_CENTRAL_FAILED_NORTH_HISTORY": [prefix + x + "Z" for x in
            ("043209725354", "044610072378", "045651436973")],
        "D_CW_ENTRY_CANDIDATE": [prefix + "050939781955Z"],
        "D_HANOK_EAST_CONTACT": [prefix + x + "Z" for x in
            ("052256192986", "052953417512", "053715963799", "055617515443")],
    }
    result = []
    for name, ids in groups.items():
        ps = tuple(primitives[i] for i in ids)
        result.append({"id": name, "primitive_ids": ids,
            "complete_geometry_links": not check_recipe_continuity(ps),
            "geometry_gaps": check_recipe_continuity(ps),
            "original_verdicts": [p.original_verdict for p in ps],
            "automatic_route_qualified": False,
            "blockers": list(COMMON_BLOCKERS) + (["ORIGINAL_FAILURE_OR_MISSING_REVIEW_PRESENT"]
                if any(not p.observed_success for p in ps) else [])})
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--template-dir", type=Path,
                        help="Optionally write the three disabled, private route-release templates.")
    args = parser.parse_args(argv)
    result = build_catalogue(args.audit_dir.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    if args.template_dir:
        args.template_dir.mkdir(parents=True, exist_ok=True)
        for destination, template in result["disabled_route_templates"].items():
            (args.template_dir / (destination.lower()+".disabled.private.json")).write_text(
                json.dumps(template, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "counts": result["counts"],
                      "signal_recontact_stages": result["signal_wait"]["measured_recontact_stage_count"],
                      "automatic_motion_authority_created": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
