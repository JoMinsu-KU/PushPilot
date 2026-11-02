"""No-device regression checks for immutable teaching/session precision binding."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import hashlib
import unittest

from backend.robot_control.session_start_reference import apply_start_reference
from backend.robot_control.site_trial_driver import SiteTrialMissionDriver
from backend.robot_control.taught_executor import ExecutionBlocked
from tests.test_site_trial_driver import fixture


class StartReferenceTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path, self.config, self.packet, self.review, _ = fixture(Path(self.directory.name))
        nominal = self.packet['contexts']['START']['pose_base']
        actual = [x+d for x, d in zip(nominal, (.001, -.001, .002, -.001, .001, -.001))]
        self.reference = {'schema': 'pushpilot.stationary-start-reference.v1',
            'session_id': 'a'*32, 'packet_sha256': self.config['packet']['sha256'],
            'review_sha256': self.config['profile_review']['sha256'],
            'nominal_start': nominal, 'observed_start': actual,
            'native_snapshot': {'session_id': 'a'*32, 'tcp_base': actual,
                'held_disarmed_idle': True, 'native_evidence_sha256': 'b'*64,
                'native_tcp_base': nominal},
            'review_reference': 'synthetic-test-only', 'operator_request': 'Synthetic no-device test.'}

    def apply(self):
        return apply_start_reference(self.packet, self.review, self.reference,
            self.config['packet']['sha256'], self.config['profile_review']['sha256'])

    def test_teaching_files_route_vertices_and_limits_remain_immutable(self):
        original, review = deepcopy(self.packet), deepcopy(self.review)
        result, bound = self.apply()
        self.assertEqual(self.packet, original)
        self.assertEqual(self.review, review)
        self.assertEqual(result['routes'], original['routes'])
        self.assertEqual(result['contexts']['START']['pose_base'], self.reference['observed_start'])
        self.assertEqual(result['contexts']['PARK']['pose_base'][:2], original['contexts']['PARK']['pose_base'][:2])
        for key in ('workspace_min_mm', 'workspace_max_mm', 'max_speed_mm_s', 'max_accel_mm_s2', 'max_step_mm'):
            self.assertEqual(bound[key], review[key])
        for row in result['primitives'].values():
            for stage in row['stages']:
                self.assertEqual(stage['start_base'][2:], stage['target_base'][2:])

    def test_larger_pose_change_is_rejected_instead_of_rebased(self):
        self.reference['observed_start'][0] += .02
        with self.assertRaises(ValueError): self.apply()

    def test_bound_config_loads_with_runtime_geometry_review(self):
        p = Path(self.directory.name) / 'session-reference.json'
        p.write_text(json.dumps(self.reference))
        self.config['session_start_reference'] = {'path': str(p), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
        self.path.write_text(json.dumps(self.config))
        driver = SiteTrialMissionDriver(self.path)
        self.assertIsNone(driver._configuration_error)
        for primitive in driver.measured.values():
            self.assertIn(primitive.geometry_sha256, driver.profile_review['allowed_geometry_sha256'])

    def test_missing_independent_native_evidence_is_rejected(self):
        self.reference['native_snapshot']['native_evidence_sha256'] = ''
        with self.assertRaises(ValueError): self.apply()

    def test_native_disagreement_is_rejected(self):
        self.reference['native_snapshot']['native_tcp_base'] = [100.]*6
        with self.assertRaises(ValueError): self.apply()

    def test_wrong_original_packet_is_rejected(self):
        self.reference['packet_sha256'] = 'e'*64
        with self.assertRaises(ValueError): self.apply()

    def test_new_session_requires_reconciliation_and_missing_link_is_clear(self):
        driver = SiteTrialMissionDriver(self.path)
        driver.session_start_reference = self.reference
        with self.assertRaises(ExecutionBlocked) as c:
            driver._validate_profile({'receiver': {'connected': False}})
        self.assertEqual(c.exception.code, 'ROBOT_CONNECTION_REQUIRED')
        with self.assertRaises(ExecutionBlocked) as c:
            driver._validate_profile({'receiver': {'connected': True, 'session_id': 'c'*32}})
        self.assertEqual(c.exception.code, 'START_REFERENCE_SESSION_CHANGED')

    def test_unrecognized_orientation_cannot_be_inferred(self):
        self.packet['contexts']['PARK']['pose_base'][5] += 45
        with self.assertRaises(ValueError): self.apply()


if __name__ == '__main__':
    unittest.main()
