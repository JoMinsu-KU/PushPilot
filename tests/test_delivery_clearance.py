"""Synthetic geometry only; no physical clearance claim."""
from copy import deepcopy
import math
import unittest
from tools.screen_delivery_clearance import repair_local_clearances
from tests.test_delivery_release import stage,pose


def packet(width=35.):
    rows=[stage("approach","approach",pose(0,width),pose()),
        stage("push","contact",pose(),pose(15)),
        stage("side1","withdraw",pose(15),pose(15,17)),
        stage("side2","withdraw",pose(15,17),pose(15,34))]
    row={"id":"example","stages":rows,"kind":"coordinate_unit","geometry_sha256":"a"*64,
        "contact_travel_limit_mm":20.,"repeatability_qualified":False}
    return {"primitives":{"example":row},"routes":{"C":{"steps":[{"id":"C-test","primitive_id":"example"}],"counts":{}}}}


class ClearanceScreenTests(unittest.TestCase):
    def run_screen(self,width=35.):
        p=packet(width);old=deepcopy(p)
        report=repair_local_clearances(p,[{"posture":pose()[2:],"normal":[1.,0.]}])
        return old,p,report

    def test_normal_departure_and_approach_preserve_actual_contact_and_endpoints(self):
        old,p,report=self.run_screen()
        a=old["primitives"]["example"]["stages"];b=p["primitives"]["example"]["stages"]
        self.assertEqual([s for s in a if s["phase"]=="contact"],[s for s in b if s["phase"]=="contact"])
        self.assertEqual(a[0]["start_base"],b[0]["start_base"])
        self.assertEqual(a[-1]["target_base"],b[-1]["target_base"])
        self.assertEqual(report["after"],[])
        self.assertFalse(report["physical_collision_free_verified"])
        for s in b:
            self.assertEqual(s["start_base"][2:],s["target_base"][2:])
            self.assertLessEqual(math.dist(s["start_base"][:2],s["target_base"][:2]),20.)
        for a,b in zip(b,b[1:]):
            self.assertEqual(a["target_base"],b["start_base"])

    def test_close_lateral_source_moves_outward_before_going_behind_contact(self):
        _,p,_=self.run_screen(15.)
        ss=p["primitives"]["example"]["stages"]
        self.assertEqual(ss[0]["target_base"],pose(0,25))
        self.assertEqual(ss[1]["target_base"],pose(-10,25))

    def test_unknown_posture_is_reported_not_guessed(self):
        p=packet();old=deepcopy(p)
        report=repair_local_clearances(p,[])
        self.assertEqual(p["primitives"],old["primitives"])
        self.assertEqual(report["after"][0]["issue"],"UNKNOWN_FACE_REFERENCE")

    def test_no_side_exit_space_is_left_unmodified_and_reported(self):
        p=packet();p["primitives"]["example"]["stages"].pop()
        report=repair_local_clearances(p,[{"posture":pose()[2:],"normal":[1.,0.]}])
        self.assertTrue(any(f["issue"]=="SIDEWAYS_WITHDRAWAL_BEFORE_CLEARANCE" for f in report["after"]))

    def test_normal_existing_path_is_unchanged(self):
        p=packet();p["primitives"]["example"]["stages"]=[
            stage("approach","approach",pose(-10),pose()),stage("push","contact",pose(),pose(15)),
            stage("back","withdraw",pose(15),pose(5))]
        old=deepcopy(p)
        report=repair_local_clearances(p,[{"posture":pose()[2:],"normal":[1.,0.]}])
        self.assertEqual(p["primitives"],old["primitives"])
        self.assertEqual(report["repairs"],[])

    def test_candidate_outside_existing_workspace_does_not_expand_limits_or_silently_apply(self):
        p=packet();old=deepcopy(p)
        report=repair_local_clearances(p,[{"posture":pose()[2:],"normal":[1.,0.]}],
            workspace_bounds=([100.,190.,6.],[140.,250.,8.]))
        self.assertEqual(p["primitives"],old["primitives"])
        self.assertEqual(report["blocked_repairs"][0]["reason"],"CANDIDATE_OUTSIDE_EXISTING_WORKSPACE")
        self.assertTrue(report["after"])
