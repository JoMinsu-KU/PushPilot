"""Offline current-site recipe compilation; no robot or service test doubles."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from tools.build_delivery_release import (compile_delivery_packet, policy_plan,
    posture_binding_template, review_template, verify_original_evidence)


START_XY = [100.,200.]


def pose(x=0., y=0., *, z=7., yaw=0.):
    return [START_XY[0]+x, START_XY[1]+y, z, 179., 0., yaw]


def stage(name, phase, start, target):
    return {"id":name,"phase":phase,"start_base":start,"target_base":target,
            "original_request_id":None,"evidence":None}


def unit(name, stages, **more):
    return {"id":name,"basis":"NEW_CURRENT_SITE_CANDIDATE","stages":stages,
        "review_after":True,"original_verdict":None,**more}


def bundle():
    seat = unit("seat",[stage("seat-contact","contact",pose(),pose(20)),
        stage("seat-withdraw","withdraw",pose(20),pose(10))],signal_gate_after="northbound")
    north = unit("north",[stage("north-approach","approach",pose(10),pose(20)),
        stage("north-contact","contact",pose(20),pose(30)),
        stage("north-withdraw","withdraw",pose(30),pose(20))])
    b = unit("office",[stage("b-contact","contact",pose(),pose(10)),
        stage("b-withdraw","withdraw",pose(10),pose(5))])
    return {"schema":"pushpilot.delivery-first-candidate-selection.v1",
        "shared_C_D_prefix":[seat],"shared_after_green_north":[north],
        "branches":{"B":[b],"C":[],"D":[]},
        "route_recipe_ids":{"B":["office"],"C":["seat","north"],"D":["seat","north"]}}


def binding(data):
    return posture_binding_template(data,fixed_z=7.,east=[179.,0.,0.],
        north=[179.,0.,90.],west=[179.,0.,180.])


class DeliveryReleaseTests(unittest.TestCase):
    def compile(self, data=None):
        data = data or bundle()
        return compile_delivery_packet(data,"1"*64,posture_binding=binding(data))

    def test_three_routes_have_concrete_stages_without_manufactured_qualification(self):
        packet = self.compile()
        self.assertEqual({v["destination"] for v in packet["routes"].values()},
            {"OFFICE_BUILDING","VILLA","HANOK"})
        self.assertFalse(packet["activation_enabled"])
        self.assertFalse(packet["repeatability_qualified"])
        self.assertEqual(packet["source_joins"],[])
        for route in packet["routes"].values():
            self.assertTrue(route["empty_return"])
            self.assertEqual(route["parking"]["mode"],"delivery_only")
            self.assertFalse(route["steps"][0]["heading_measurement_available"])

    def test_green_recontact_is_separate_and_cannot_replay_seating(self):
        packet = self.compile()
        steps = packet["routes"]["C"]["steps"]
        gate = steps[0]["signal_gate"]
        recontact = packet["primitives"][gate["recontact_primitive_id"]]
        following = packet["primitives"][steps[1]["primitive_id"]]
        self.assertEqual([s["phase"] for s in recontact["stages"]],["approach"])
        self.assertEqual([s["phase"] for s in following["stages"]],["contact","withdraw"])
        self.assertFalse(gate["seating_replay_allowed"])
        self.assertTrue(gate["entry_recheck_required"])
        self.assertEqual(recontact["target_context_id"],gate["last_contact_context_id"])
        self.assertEqual(following["source_context_id"],gate["last_contact_context_id"])

    def test_original_receipt_and_original_posture_survive_explicit_rebinding(self):
        data = bundle()
        s = data["branches"]["B"][0]["stages"][0]
        s["start_base"][2] = s["target_base"][2] = 7.0005
        s["evidence"] = {"container":"original","member":"result.json","sha256":"2"*64}
        s["original_request_id"] = "historical-id-for-provenance-only"
        data["branches"]["B"][0]["stages"][1]["start_base"][2] = 7.0005
        data["branches"]["B"][0]["stages"][1]["target_base"][2] = 7.0005
        packet = self.compile(data)
        result = packet["primitives"]["office"]["stages"][0]
        self.assertEqual(result["start_base"][2],7.)
        self.assertEqual(result["original"]["start_base"][2],7.0005)
        self.assertEqual(result["original"]["evidence"],s["evidence"])
        self.assertEqual(result["geometry_basis"],"derived_posture_binding")

    def test_no_posture_binding_never_claims_an_activated_packet(self):
        packet = compile_delivery_packet(bundle(),"1"*64)
        self.assertIn("EXPLICIT_FIXED_Z_POSTURE_BINDING_REQUIRED",packet["blockers"])
        self.assertFalse(packet["activation_enabled"])

    def test_a_large_source_gap_is_rejected_instead_of_fitted(self):
        data = bundle()
        data["shared_after_green_north"][0]["stages"][0]["start_base"][0] += 1.
        with self.assertRaisesRegex(ValueError,"source gap"):
            self.compile(data)

    def test_unknown_or_large_posture_changes_are_rejected(self):
        data = bundle()
        data["branches"]["B"][0]["stages"][0]["target_base"][5] = 3.
        with self.assertRaisesRegex(ValueError,"literal family"):
            self.compile(data)

    def test_single_stage_cannot_exceed_twenty_mm(self):
        data = bundle()
        data["shared_C_D_prefix"][0]["stages"][0]["target_base"][0] += .2
        with self.assertRaisesRegex(ValueError,"20 mm"):
            self.compile(data)

    def test_total_contact_limit_cannot_be_hidden_in_many_stages(self):
        data = bundle()
        data["branches"]["B"][0]["stages"] = [
            stage("one","contact",pose(),pose(20)),
            stage("two","contact",pose(20),pose(40)),
            stage("three","contact",pose(40),pose(50)),
            stage("release","withdraw",pose(50),pose(40))]
        with self.assertRaisesRegex(ValueError,"40 mm"):
            self.compile(data)

    def test_shortest_empty_return_has_no_printed_road_constraint(self):
        data = bundle()
        data["branches"]["B"][0]["stages"] = [
            stage("one","contact",pose(),pose(10,10)),
            stage("release","withdraw",pose(10,10),pose(20,20))]
        packet = self.compile(data)
        route = packet["routes"]["B"]
        result = packet["primitives"][route["empty_return"][0]]
        self.assertEqual(len(result["stages"]),2)
        for s in result["stages"]:
            self.assertEqual(s["phase"],"empty")
            self.assertIsNone(s["original"]["evidence"])
            self.assertEqual(s["geometry_basis"],"current_site_candidate")
            self.assertEqual(s["start_base"][2:],s["target_base"][2:])
        self.assertEqual(result["stages"][-1]["target_base"][:2],START_XY)

    def test_changed_final_orientation_gets_a_separate_unloaded_restore(self):
        data = bundle()
        data["branches"]["B"][0]["stages"] = [stage("release","empty",pose(),pose(5))]
        data["branches"]["B"] += [unit("rotate",[stage("rot","wrist",pose(5),pose(5,yaw=90.))]),
            unit("northcontact",[stage("n-approach","approach",pose(5,yaw=90.),pose(5,1,yaw=90.)),
                stage("n-contact","contact",pose(5,1,yaw=90.),pose(5,10,yaw=90.)),
                stage("n-release","withdraw",pose(5,10,yaw=90.),pose(5,5,yaw=90.))])]
        data["route_recipe_ids"]["B"] += ["rotate","northcontact"]
        packet = self.compile(data)
        ids = packet["routes"]["B"]["empty_return"]
        self.assertEqual(len(ids),2)
        wrist = packet["primitives"][ids[-1]]
        self.assertEqual(wrist["kind"],"wrist_edge")
        self.assertTrue(wrist["empty_tool"])
        self.assertIsNone(wrist["stages"][0]["original"]["evidence"])
        self.assertTrue(wrist["wrist"]["current_joint_source_and_target_ik_required"])

    def test_policy_adapter_uses_reviewed_trial_fields_not_qualified_true(self):
        packet = self.compile()
        plan = policy_plan(packet,"C",{},"4"*64,plan_id="new-mission")
        self.assertEqual(plan["release_mode"],"site_trial")
        p = plan["steps"][0]["primitive"]
        self.assertFalse(p["qualified"])
        self.assertEqual(p["qualification_sha256"],"0"*64)
        self.assertEqual(p["current_site_review_sha256"],"4"*64)
        self.assertEqual(plan["steps"][0]["signal_gate"]["recontact"]["target_context_id"],
                         plan["steps"][1]["primitive"]["source_context_id"])

    def test_review_template_is_pending_and_bound_to_exact_geometry(self):
        packet = self.compile()
        review = review_template(packet)
        self.assertEqual(review["status"],"pending")
        self.assertIsNone(review["current_profile_sha256"])
        self.assertEqual(review["geometry_manifest_sha256"],packet["geometry_manifest_sha256"])
        self.assertFalse(review["repeatability_qualified"])

    def test_original_evidence_hashes_are_verified_not_only_copied(self):
        data = bundle()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"receipt.json"
            path.write_bytes(b'{"state":"complete"}')
            ref = {"container":directory,"member":"receipt.json",
                   "sha256":hashlib.sha256(path.read_bytes()).hexdigest()}
            s = data["branches"]["B"][0]["stages"][0]
            s["evidence"],s["original_request_id"] = ref,"original-request"
            self.assertEqual(verify_original_evidence(data)["member_count"],1)
            path.write_bytes(b'{"state":"failed"}')
            with self.assertRaisesRegex(ValueError,"member hash changed"):
                verify_original_evidence(data)

    def test_internal_gap_cannot_become_a_synthetic_connector(self):
        data = bundle()
        data["branches"]["B"][0]["stages"][1]["start_base"][0] += .01
        with self.assertRaisesRegex(ValueError,"internal geometry discontinuity"):
            self.compile(data)

    def test_three_collinear_contacts_are_explicit_new_subsegments_with_originals(self):
        data = bundle()
        original = [stage("one","contact",pose(),pose(10)),
            stage("two","contact",pose(10),pose(20)),stage("three","contact",pose(20),pose(30))]
        data["branches"]["B"][0]["stages"] = original+[
            stage("release","withdraw",pose(30),pose(20))]
        result = self.compile(data)["primitives"]["office"]
        contacts = [s for s in result["stages"] if s["phase"] == "contact"]
        self.assertEqual(len(contacts),2)
        for s in contacts:
            self.assertEqual(s["derivation"],"collinear_contact_resubdivision")
            self.assertEqual(s["original"]["supporting_segments"],original)
            self.assertIsNone(s["original"]["evidence"])

    def test_leading_empty_traverse_is_a_distinct_route_step(self):
        data = bundle()
        data["branches"]["B"][0]["stages"] = [stage("clear","empty",pose(),pose(3)),
            stage("approach","approach",pose(3),pose(5)),
            stage("contact","contact",pose(5),pose(10)),stage("release","withdraw",pose(10),pose(7))]
        packet = self.compile(data)
        steps = packet["routes"]["B"]["steps"]
        self.assertEqual(len(steps),2)
        self.assertTrue(packet["primitives"][steps[0]["primitive_id"]]["empty_tool"])
        self.assertEqual(packet["primitives"][steps[1]["primitive_id"]]["stages"][0]["phase"],"approach")

    def test_west_return_uses_two_directed_wrist_edges(self):
        data = bundle()
        data["branches"]["B"][0]["stages"] = [stage("clear","empty",pose(),pose(3))]
        data["branches"]["B"] += [unit("n",[stage("n","wrist",pose(3),pose(3,yaw=90.))]),
            unit("w",[stage("w","wrist",pose(3,yaw=90.),pose(3,yaw=180.))]),
            unit("contact",[stage("approach","approach",pose(3,yaw=180.),pose(5,yaw=180.)),
                stage("contact","contact",pose(5,yaw=180.),pose(10,yaw=180.)),
                stage("release","withdraw",pose(10,yaw=180.),pose(7,yaw=180.))])]
        data["route_recipe_ids"]["B"] += ["n","w","contact"]
        packet = self.compile(data)
        returns = [packet["primitives"][pid] for pid in packet["routes"]["B"]["empty_return"]]
        self.assertEqual([p["kind"] for p in returns],["empty_path","wrist_edge","wrist_edge"])
        self.assertEqual([p["wrist"]["requested_delta_j6_deg"] for p in returns[1:]],[89.999,89.999])

    def test_policy_adapter_roundtrips_the_real_dataclasses(self):
        from backend.robot_control.mission_driver import plan_from_dict
        site = {"installation_id":"test-site","map_sha256":"1"*64,"calibration_id":"test-view",
            "tool_id":"test-tool","car_id":"test-car","camera_epoch":"test-epoch"}
        packet = self.compile()
        for code in "BCD":
            parsed = plan_from_dict(policy_plan(packet,code,site,"2"*64,plan_id="test-"+code))
            self.assertEqual(parsed.release_mode,"site_trial")
            self.assertFalse(any(s.primitive.qualified for s in parsed.steps))

    def test_shared_vertex_normalization_is_explicit_and_preserves_original_pose(self):
        data=bundle()
        original=data["shared_after_green_north"][0]["stages"][0]["start_base"]
        original[0] += 1e-10
        packet=self.compile(data)
        row=packet["primitives"]["north/signal-recontact"]
        s=row["stages"][0]
        self.assertEqual(s["original"]["start_base"],original)
        self.assertNotEqual(s["start_base"],original)
        self.assertEqual(s["start_base"],packet["contexts"][row["source_context_id"]]["pose_base"])
        self.assertLessEqual(s["numerical_shared_vertex_normalization"]["start"]["maximum_component_difference"],1e-9)
        for p in packet["primitives"].values():
            self.assertEqual(p["stages"][0]["start_base"],packet["contexts"][p["source_context_id"]]["pose_base"])
            self.assertEqual(p["stages"][-1]["target_base"],packet["contexts"][p["target_context_id"]]["pose_base"])


if __name__ == "__main__":
    unittest.main()
