"""Endpoint revisions preserve contact evidence, return continuity and limits."""
from copy import deepcopy
import unittest

from tests.test_delivery_release import bundle, binding, pose, stage, unit
from tools.build_delivery_release import compile_delivery_packet
from tools.revise_delivery_endpoint import select_delivery_endpoint


class DeliveryEndpointTests(unittest.TestCase):
    def packet(self):
        data = bundle()
        data['branches']['C'] = [unit('extra', [
            stage('in', 'approach', pose(20), pose(30)),
            stage('push', 'contact', pose(30), pose(40)),
            stage('out', 'withdraw', pose(40), pose(30))])]
        data['route_recipe_ids']['C'].append('extra')
        return compile_delivery_packet(data, '1'*64, posture_binding=binding(data))

    def test_selected_endpoint_ends_route_without_rewriting_loaded_geometry_or_other_routes(self):
        original = self.packet()
        before = deepcopy(original)
        revised = select_delivery_endpoint(original, 'C', 'C-step-2', reason='Operator selected this arrival.')
        self.assertEqual(original, before)
        route = revised['routes']['C']
        self.assertEqual([s['id'] for s in route['steps']], ['C-step-1', 'C-step-2'])
        self.assertEqual([s['at_goal'] for s in route['steps']], [False, True])
        self.assertEqual(route['parking']['mode'], 'delivery_only')
        self.assertEqual(route['empty_return'], route['early_arrival_returns']['C-step-2'])
        for code in ('B', 'D'):
            self.assertEqual(original['routes'][code], revised['routes'][code])
        for pid, old in original['primitives'].items():
            self.assertEqual(old, revised['primitives'][pid])
        self.assertFalse(revised['endpoint_revisions'][-1]['historical_reviews_rewritten'])

    def test_long_return_is_partitioned_at_existing_vertices_and_still_reaches_start(self):
        packet = self.packet()
        route = packet['routes']['C']
        pid = route['early_arrival_returns']['C-step-2'][0]
        row = packet['primitives'][pid]
        a = row['stages'][0]['start_base']
        b = [a[0]-220, *a[1:]]
        packet['contexts'][route['start_context_id']]['pose_base'] = b
        row['stages'] = []
        prior = a
        for i in range(11):
            target = [a[0]-20*(i+1), *a[1:]]
            row['stages'].append(stage(str(i), 'empty', prior, target))
            prior = target
        revised = select_delivery_endpoint(packet, 'C', 'C-step-2', reason='Selected final checkpoint.')
        returned = [revised['primitives'][p] for p in revised['routes']['C']['empty_return']]
        self.assertGreater(len(returned), 1)
        self.assertEqual([s for p in returned for s in p['stages']], row['stages'])
        for left, right in zip(returned, returned[1:]):
            self.assertEqual(left['target_context_id'], right['source_context_id'])
            self.assertEqual(left['stages'][-1]['target_base'], right['stages'][0]['start_base'])
        self.assertEqual(returned[-1]['target_context_id'], route['start_context_id'])
        for part in returned:
            points = [part['stages'][0]['start_base']] + [s['target_base'] for s in part['stages']]
            self.assertLessEqual(max(p[0] for p in points)-min(p[0] for p in points), 150)

    def test_signal_gate_or_missing_return_cannot_become_terminal_shortcut(self):
        packet = self.packet()
        with self.assertRaises(ValueError):
            select_delivery_endpoint(packet, 'C', 'C-step-1', reason='Cannot skip a gate.')
        del packet['routes']['C']['early_arrival_returns']['C-step-2']
        with self.assertRaises(ValueError):
            select_delivery_endpoint(packet, 'C', 'C-step-2', reason='Missing return.')


if __name__ == '__main__':
    unittest.main()
