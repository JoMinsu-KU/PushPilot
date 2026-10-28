"""Coordinate-only teaching proposals do not inherit map or motion authority."""
import math
import unittest

from backend.robot_control.taught_roads import TaughtPoint, propose_taught_roads, next_fixed_pose_target
from tools.preview_taught_roads import preview


def point(name, x, y, fixed=(20,90,0,30)):
    return TaughtPoint(name,(x,y,*fixed),('abcdef'[ord(name[0]) % 6])*64)


def points():
    return (point('A',0,0),point('B',100,0),point('C',0,60),point('D',100,60),point('E',50,30))


class TaughtRoadTests(unittest.TestCase):
    def test_intersections_and_direct_taught_destinations(self):
        roads=propose_taught_roads(points())
        self.assertEqual(roads.south_junction_xy,(50,0))
        self.assertEqual(roads.north_junction_xy,(50,60))
        route=roads.route_preview('B',point('START',10,0))
        self.assertEqual([p['to'] for p in route['legs']],['SOUTH_JUNCTION_PROPOSED','B'])
        self.assertEqual([p['length_mm'] for p in route['legs']],[40,50])
        self.assertEqual(route['goal_pose_base_mm_deg'],[100,0,20,90,0,30])
        self.assertFalse(route['map_transform_used'])
        self.assertFalse(route['execution_ready'])
        self.assertFalse(route['vehicle_arrival_verified'])
        self.assertEqual(route['fresh_start_observation_sha256'],point('START',10,0).observation_sha256)

    def test_opposite_frontage_turns_are_proposals_not_rotation_commands(self):
        roads=propose_taught_roads(points())
        for destination,last_turn in [('C',90),('D',-90)]:
            with self.subTest(destination=destination):
                route=roads.route_preview(destination,point('START',10,0))
                self.assertEqual([p['to'] for p in route['legs']],['SOUTH_JUNCTION_PROPOSED','E','NORTH_JUNCTION_PROPOSED',destination])
                self.assertEqual([p['relative_turn_deg'] for p in route['legs']],[None,90,0,last_turn])
                self.assertTrue(all(not p['turn_contact_qualified'] for p in route['legs']))
                self.assertFalse(route['motion_authority'])
                self.assertFalse(route['automatic_replay'])

    def test_translated_rotated_base_preserves_geometry(self):
        def moved(x,y):
            angle=math.radians(31)
            return 13+x*math.cos(angle)-y*math.sin(angle),-27+x*math.sin(angle)+y*math.cos(angle)
        shifted=tuple(point(p.id,*moved(*p.pose_base_mm_deg[:2])) for p in points())
        roads=propose_taught_roads(shifted)
        for actual,expected in [(roads.south_junction_xy,moved(50,0)),(roads.north_junction_xy,moved(50,60))]:
            self.assertAlmostEqual(math.dist(actual,expected),0,places=10)
        route=roads.route_preview('C',point('START',*moved(10,0)))
        self.assertAlmostEqual(route['start_cross_track_from_AB_mm'],0,places=10)
        self.assertAlmostEqual(sum(p['length_mm'] for p in route['legs']),150,places=10)

    def test_reject_bad_evidence_or_changed_pose(self):
        with self.assertRaises(ValueError):
            TaughtPoint('A',(0,0,20,90,0,30),'not-a-hash')
        for value in [True,float('nan'),float('inf'),'0']:
            with self.subTest(value=value),self.assertRaises(ValueError):
                point('A',value,0)
        with self.assertRaises(ValueError):
            propose_taught_roads(points()[:-1])
        for fixed in [(20.1,90,0,30),(20,90,0,31)]:
            changed=list(points());changed[2]=point('C',0,60,fixed)
            with self.subTest(fixed=fixed),self.assertRaises(ValueError):
                propose_taught_roads(changed)
        with self.assertRaises(ValueError):
            propose_taught_roads(points()).route_preview('C',point('START',0,0,(21,90,0,30)))

    def test_reject_reversed_skewed_or_unsupported_connector_geometry(self):
        cases=[]
        reverse=list(points());reverse[2],reverse[3]=point('C',100,60),point('D',0,60);cases.append(reverse)
        skew=list(points());skew[3]=point('D',100,100);cases.append(skew)
        outside=list(points());outside[4]=point('E',150,30);cases.append(outside)
        beyond=list(points());beyond[4]=point('E',50,80);cases.append(beyond)
        degenerate=list(points());degenerate[1]=point('B',0,0);cases.append(degenerate)
        for index,case in enumerate(cases):
            with self.subTest(index=index),self.assertRaises(ValueError):
                propose_taught_roads(case)
        with self.assertRaises(ValueError):
            propose_taught_roads(points()).route_preview('UNKNOWN',point('START',10,0))
        with self.assertRaises(ValueError):
            propose_taught_roads(points(),max_frontage_disagreement_deg=True)

    def test_next_target_is_rebased_on_actual_without_z_or_yaw_change(self):
        actual=(10,0,20,90,0,30);end=(20,0,20,90,0,30)
        first=next_fixed_pose_target(actual,end,2)
        self.assertEqual(first,(12,0,20,90,0,30))
        # Actual drift is preserved; no stale previous target is silently replayed.
        drifted=(11.8,.3,20,90,0,30)
        following=next_fixed_pose_target(drifted,end,2)
        self.assertLessEqual(math.dist(following[:2],drifted[:2]),2)
        self.assertNotEqual(following,(14,0,20,90,0,30))
        self.assertIsNone(next_fixed_pose_target(end,end,2))
        with self.assertRaises(ValueError):
            next_fixed_pose_target(actual,(20,0,20,90,0,120),2)

    def test_no_historical_start_substitution_or_unreviewed_backtracking(self):
        data={'points':[{'id':p.id,'pose_base_mm_deg':p.pose_base_mm_deg,
                         'observation_sha256':p.observation_sha256} for p in points()]}
        result=preview(data)
        self.assertTrue(result['start_required'])
        self.assertNotIn('routes',result)
        self.assertFalse(result['motion_issued'] or result['execution_ready'])
        roads=propose_taught_roads(points())
        for x in (-1,51,100):
            with self.subTest(x=x),self.assertRaises(ValueError):
                roads.route_preview('B',point('START',x,0))
        with self.assertRaises(ValueError):
            preview({**data,'activate':True})


if __name__=='__main__':
    unittest.main()
