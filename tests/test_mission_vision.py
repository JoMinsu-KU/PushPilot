"""Physical MUSE adapter contracts with synthetic images and mocked HTTP only."""
from __future__ import annotations

import base64
from copy import deepcopy
import hashlib
import json
import unittest

import httpx

from backend.robot_control.mission_vision import MetaMissionVision, exclusive_signal, validate_observation, signal_detail_content
from backend.scene import SceneError
from tests.test_live_review_provider import envelope, frame_fixture


def observation(**changes):
    value = {"verdict": "PASS", "car_visible": True, "expected_progress": True,
        "heading_matches_expected": True, "arrived": False, "at_fixed_start": False,
        "car_unchanged_since_stop": True, "signal_target_matches": True, "mask_in_transition": False,
        "within_road": True, "car_zone_id": "SOUTH_WAIT", "occlusion_cause": "NONE",
        "red_face": "VISIBLE", "green_face": "COVERED",
        "summary": "Synthetic paper target: red is visible and green is intentionally covered.",
        "limitations": ["Synthetic fixture; no real motion or metrology evidence."]}
    value.update(changes)
    return value


class PhysicalSignalContractTests(unittest.TestCase):
    def test_signal_detail_preserves_source_pixels_and_marks_sample_order(self):
        import cv2
        import numpy as np
        from tests.test_mission_progress import image
        frames=(image(25),image(180))
        content=signal_detail_content(frames,{'pixel_polygon':[[70,70],[75,70],[75,75],[70,75]]})
        sheet=cv2.imdecode(np.frombuffer(base64.b64decode(content[1]['image_url']['url'].split(',',1)[1]),np.uint8),cv2.IMREAD_COLOR)
        # Bounds are the polygon plus a clamped 64px margin: [6,6,120,80].
        for index,frame in enumerate(frames):
            source=cv2.imdecode(np.frombuffer(frame['data'],np.uint8),cv2.IMREAD_COLOR)
            panel=sheet[48:,index*228:(index+1)*228]
            np.testing.assert_array_equal(panel[::2,::2],source[6:80,6:120])
            self.assertIn(frame['metadata']['sha256'],content[0]['text'])
        with self.assertRaises(SceneError):
            signal_detail_content(frames,{'pixel_polygon':[[float('nan'),0],[1,0],[1,1]]})

    def test_paddle_over_green_is_red_and_paddle_over_red_is_green(self):
        self.assertEqual(exclusive_signal(observation()), ("RED", True))
        self.assertEqual(exclusive_signal(observation(red_face="COVERED", green_face="VISIBLE")), ("GREEN", True))

    def test_both_none_partial_or_unidentified_target_never_grants_green(self):
        for red, green in (("VISIBLE", "VISIBLE"), ("COVERED", "COVERED"),
                           ("UNCERTAIN", "VISIBLE"), ("VISIBLE", "UNCERTAIN"),
                           ("COVERED", "UNCERTAIN"), ("UNCERTAIN", "COVERED"), ("UNCERTAIN", "UNCERTAIN")):
            with self.subTest(red=red, green=green):
                self.assertEqual(exclusive_signal(observation(red_face=red, green_face=green)), ("UNKNOWN", False))
        self.assertEqual(exclusive_signal(observation(red_face="COVERED", green_face="VISIBLE",
                                                      signal_target_matches=False)), ("UNKNOWN", False))

    def test_hand_swap_transition_is_unknown_even_if_green_currently_visible(self):
        value = observation(red_face="COVERED", green_face="VISIBLE", mask_in_transition=True,
                            occlusion_cause="HAND")
        self.assertEqual(exclusive_signal(value), ("UNKNOWN", False))

    def test_schema_does_not_allow_commands_or_metric_pose_claims(self):
        for key in ("tcp", "command", "heading_deg", "admit_crossing"):
            with self.subTest(key=key), self.assertRaises(SceneError):
                validate_observation(observation(**{key: 1}))

    def test_schema_strictly_checks_boolean_null_text_and_lists(self):
        cases = [None, [], {}, observation(car_visible=1), observation(within_road=0),
            observation(verdict=["PASS"]), observation(red_face="RED"), observation(summary=" "),
            observation(summary="a" * 801), observation(car_zone_id=""), observation(car_zone_id="a" * 121),
            observation(limitations=["a"] * 9), observation(limitations=[None]), observation(limitations=[" "]),
            observation(limitations=["a" * 301]), observation(mask_in_transition="false")]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(SceneError) as raised:
                validate_observation(case)
            self.assertEqual(raised.exception.code, "MUSE_SCHEMA")

    def test_unknown_car_road_and_zone_remain_unknown_without_filling_values(self):
        raw = observation(verdict="UNCERTAIN", car_visible=False, within_road=None, car_zone_id=None,
                           occlusion_cause="HOSE")
        result = validate_observation(raw)
        self.assertEqual(result, raw)
        result["limitations"].append("changed copy")
        self.assertNotEqual(result, raw)


class PhysicalMissionVisionTests(unittest.IsolatedAsyncioTestCase):
    def provider(self, handler, key="synthetic-not-a-secret"):
        return MetaMissionVision(key, transport=httpx.MockTransport(handler))

    async def test_two_signal_frames_use_one_request_and_preserve_each_original(self):
        reference, first, second = frame_fixture(1), frame_fixture(10), frame_fixture(30)
        first["metadata"]["captured_at"], second["metadata"]["captured_at"] = 12., 12.35
        green = observation(red_face="COVERED", green_face="VISIBLE")
        calls = []
        def handler(request):
            calls.append(request)
            payload = json.loads(request.content)
            self.assertEqual(payload["max_completion_tokens"], 2200)
            prompt = payload['messages'][0]['content']
            self.assertIn('a narrow exposed rim or small edge crescent', prompt)
            self.assertIn('Both substantially exposed faces', prompt)
            self.assertIn('Small hand tremor', prompt)
            self.assertIn('substantial shift exposing the covered disk', prompt)
            self.assertIn('PHYSICAL paper target', prompt)
            context_text=payload['messages'][1]['content'][0]['text']
            self.assertNotIn('old motion expectation',context_text)
            self.assertNotIn('expected_heading_deg',context_text)
            images = [x["image_url"]["url"] for x in payload["messages"][1]["content"] if x["type"] == "image_url"]
            self.assertEqual([base64.b64decode(x.split(",", 1)[1]) for x in images],
                             [x["data"] for x in (reference, first, second)])
            return httpx.Response(200, json=envelope({"samples": [green, green]}))
        result = await self.provider(handler).observe_signal_pair(frames=(first, second),
            context={'expected_visual':'old motion expectation','expected_heading_deg':90}, before=reference)
        self.assertEqual(result, [green, green])
        self.assertEqual(len(calls), 1)

    async def test_signal_pair_count_and_duplicate_frames_cannot_supply_stability(self):
        first, second = frame_fixture(10), frame_fixture(30)
        first["metadata"]["captured_at"], second["metadata"]["captured_at"] = 12., 12.35
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(200, json=envelope({"samples": [observation()]}))
        with self.assertRaises(SceneError):
            await self.provider(handler).observe_signal_pair(frames=(first, second), context={}, before=first)
        with self.assertRaises(SceneError):
            await self.provider(handler).observe_signal_pair(frames=(first, first), context={}, before=first)
        self.assertEqual(len(calls), 1)

    async def test_original_reference_current_bytes_and_source_context_are_unchanged(self):
        before, current = frame_fixture(10), frame_fixture(50)
        source = {"mission_id": "m", "stop_id": "s", "signal_target": {"id": "paper-south"},
                  "expected_visual": "Synthetic outcome", "source_captured_at": 12.}
        untouched, calls = deepcopy(source), []
        def handler(request):
            calls.append(request)
            payload = json.loads(request.content)
            self.assertEqual(payload["model"], "muse-spark-1.3")
            content = payload["messages"][1]["content"]
            self.assertEqual(json.loads(content[0]["text"].split(": ", 1)[1]), source)
            self.assertTrue(content[1]["text"].startswith("REFERENCE live frame metadata"))
            self.assertTrue(content[3]["text"].startswith("CURRENT live frame metadata"))
            image_urls = [part["image_url"]["url"] for part in content if part["type"] == "image_url"]
            for uri, original in zip(image_urls, (before, current)):
                data = base64.b64decode(uri.split(",", 1)[1])
                self.assertEqual(data, original["data"])
                self.assertEqual(hashlib.sha256(data).hexdigest(), original["metadata"]["sha256"])
            prompt = payload["messages"][0]["content"]
            for requirement in ("TWO permanently printed", "black circular paper paddle", "cable tie",
                                "Both visible, neither visible", "Do not infer GREEN", "not TCP coordinates",
                                "untrusted task data", "reference photos are hypotheses", "visibly unchanged car pose"):
                self.assertIn(requirement, prompt)
            self.assertTrue(payload["response_format"]["json_schema"]["strict"])
            self.assertFalse(payload["response_format"]["json_schema"]["schema"]["additionalProperties"])
            return httpx.Response(200, json=envelope(observation()))
        result = await self.provider(handler).observe(frame=current, context=source, before=before)
        self.assertEqual(result, observation())
        self.assertEqual(source, untouched)
        self.assertEqual(len(calls), 1)

    async def test_current_frame_only_does_not_invent_reference_image(self):
        def handler(request):
            content = json.loads(request.content)["messages"][1]["content"]
            self.assertEqual(sum(part["type"] == "image_url" for part in content), 1)
            self.assertFalse(any("REFERENCE" in part.get("text", "") for part in content))
            return httpx.Response(200, json=envelope(observation(car_unchanged_since_stop=False)))
        result = await self.provider(handler).observe(frame=frame_fixture(), context={"synthetic": True})
        self.assertFalse(result["car_unchanged_since_stop"])

    async def test_delivery_only_prompt_separates_arrival_from_parallel_parking_and_retains_raw_verdict(self):
        task = {"parking_mode": "delivery_only", "goal_arrival_check": True,
                "completed_primitive_id": "synthetic-delivery", "expected_visual": "Reach the named destination.",
                "numeric_pose_authority": False}
        for verdict in ("PASS", "FAIL", "UNCERTAIN"):
            def handler(request):
                payload = json.loads(request.content)
                prompt = payload["messages"][0]["content"]
                for requirement in ("parking_mode is delivery_only AND goal_arrival_check is true",
                                    "wholly within the road", "parallel angle and lateral parking alignment are not",
                                    "An earlier FAIL/UNCERTAIN is not rewritten",
                                    "Additional displacement from REFERENCE is not required",
                                    "step number or completed TCP motion never proves arrival",
                                    "bound completed primitive's expected_visual", "may intentionally leave the car diagonal",
                                    "visible wrong turn", "not a measurement request"):
                    self.assertIn(requirement, prompt)
                serialized_task = json.loads(payload["messages"][1]["content"][0]["text"].split(": ", 1)[1])
                self.assertEqual(serialized_task, task)
                return httpx.Response(200, json=envelope(observation(verdict=verdict, arrived=True,
                    heading_matches_expected=False)))
            with self.subTest(verdict=verdict):
                result = await self.provider(handler).observe(frame=frame_fixture(), context=task)
                self.assertEqual(result["verdict"], verdict)
                self.assertFalse(result["heading_matches_expected"])
                self.assertTrue(result["arrived"])

    async def test_original_hash_mismatch_fails_before_any_http_request(self):
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(200, json=envelope(observation()))
        current = frame_fixture()
        current["metadata"]["sha256"] = "f" * 64
        with self.assertRaises(SceneError) as raised:
            await self.provider(handler).observe(frame=current, context={})
        self.assertEqual(raised.exception.code, "LIVE_REVIEW_FRAME")
        self.assertEqual(calls, [])

    async def test_truncation_refusal_and_malformed_provider_outputs_are_rejected(self):
        cases = [envelope(observation(), finish="length"), envelope(observation(), refusal="private refusal"),
            {"choices": []}, {"choices": [{"finish_reason": "stop", "message": {"content": "private bad JSON"}}]},
            envelope(observation(car_visible="true")), envelope({**observation(), "robot_command": "move"})]
        for case in cases:
            calls = []
            def handler(request):
                calls.append(request)
                return httpx.Response(200, json=case)
            with self.subTest(case=case), self.assertRaises(SceneError) as raised:
                await self.provider(handler).observe(frame=frame_fixture(), context={})
            self.assertEqual(raised.exception.status_code, 502)
            self.assertNotIn("private", str(raised.exception))
            self.assertNotIn("synthetic-not-a-secret", str(raised.exception))
            self.assertEqual(len(calls), 1)

    async def test_redirect_provider_errors_and_transport_failures_are_not_retried(self):
        for status in (302, 401, 429, 503):
            calls = []
            def handler(request):
                calls.append(request)
                return httpx.Response(status, headers={"location": "https://invalid.example"}, text="private upstream")
            with self.subTest(status=status), self.assertRaises(SceneError):
                await self.provider(handler).observe(frame=frame_fixture(), context={})
            self.assertEqual(len(calls), 1)
        calls = []
        def failing(request):
            calls.append(request)
            raise httpx.ReadTimeout("private timeout", request=request)
        with self.assertRaises(SceneError):
            await self.provider(failing).observe(frame=frame_fixture(), context={})
        self.assertEqual(len(calls), 1)

    async def test_missing_api_key_has_no_network_call(self):
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(200, json=envelope(observation()))
        with self.assertRaises(SceneError) as raised:
            await self.provider(handler, key="").observe(frame=frame_fixture(), context={})
        self.assertEqual(raised.exception.code, "MUSE_NOT_CONFIGURED")
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
