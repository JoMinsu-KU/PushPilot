"""Offline native-frame action and signal provider contract tests only."""
from __future__ import annotations

import base64
from copy import deepcopy
import hashlib
import json
import unittest

import cv2
import httpx
import numpy as np

from backend.live_review_provider import MetaLiveReviewProvider, validate_signal_result
from backend.scene import SceneError


def frame_fixture(position=10) -> dict:
    image = np.full((64, 96, 3), 230, dtype=np.uint8)
    cv2.rectangle(image, (position, 25), (position + 14, 40), (40, 40, 190), -1)
    success, encoded = cv2.imencode(".jpg", image)
    assert success
    data = encoded.tobytes()
    return {"data": data, "metadata": {
        "id": str(position), "sha256": hashlib.sha256(data).hexdigest(), "source": "live_preview",
        "timestamp_source": "host_receive", "simulation_only": True, "physical_motion_authority": False,
    }}


def action_inputs() -> dict:
    return {
        "before": frame_fixture(10), "after": frame_fixture(50),
        "map": {"id": "test-town", "version": "1", "geometry_hash": "c" * 64},
        "server_action": {"id": "action-1", "kind": "PUSH", "source": "simulation", "receipt": "simulation-done-1"},
        "expected_visual": "Synthetic evaluation: compare the depicted test object's positions.",
    }


def signal_inputs() -> dict:
    return {
        "frame": frame_fixture(), "map": {"id": "test-town", "version": "1", "geometry_hash": "c" * 64},
        "signal_target": {
            "id": "paper-west", "description": "The separate paper card controlling the incoming western approach.",
            "approach": "west", "bounds_mm": [10, 20, 25, 35],
            "pixel_polygon": [[30, 20], [45, 20], [45, 35], [30, 35]],
        },
        "server_stop": {
            "mission_id": "mission-1", "plan_id": "plan-1", "step_id": "stop-1", "junction_id": "J1",
            "approach": "west", "receipt": "simulated-stop-1", "request_id": "request-1", "source": "simulation",
        },
    }


def action_result() -> dict:
    return {
        "verdict": "PASS", "observed": "The synthetic test object appears farther right in the AFTER image.",
        "summary": "The depicted visual change is supported.",
        "limitations": ["Synthetic images and a simulation receipt do not establish physical movement."],
    }


def signal_result(color="RED") -> dict:
    return {"color": color, "visible": color != "UNKNOWN", "summary": "The specified synthetic paper target is readable.",
            "limitations": ["Synthetic fixture; not a physical stop or crossing receipt."]}


def envelope(result, *, finish="stop", refusal=None):
    return {"choices": [{"finish_reason": finish, "message": {"content": json.dumps(result), "refusal": refusal}}]}


class LiveReviewProviderTests(unittest.IsolatedAsyncioTestCase):
    def provider(self, handler):
        return MetaLiveReviewProvider("test-only-not-a-secret", transport=httpx.MockTransport(handler))

    def assert_frames(self, content, frames):
        images = [part["image_url"]["url"] for part in content if part["type"] == "image_url"]
        self.assertEqual(len(images), len(frames))
        for uri, frame in zip(images, frames):
            self.assertTrue(uri.startswith("data:image/jpeg;base64,"))
            original = base64.b64decode(uri.split(",", 1)[1])
            self.assertEqual(original, frame["data"])
            self.assertEqual(hashlib.sha256(original).hexdigest(), frame["metadata"]["sha256"])

    async def test_action_sends_original_before_after_in_order_and_simulation_context(self):
        inputs, calls = action_inputs(), []
        original = deepcopy(inputs)

        async def handler(request):
            calls.append(request)
            self.assertEqual(str(request.url), MetaLiveReviewProvider.endpoint)
            self.assertEqual(request.headers["authorization"], "Bearer test-only-not-a-secret")
            self.assertEqual(request.extensions["timeout"]["connect"], 5.0)
            self.assertEqual(request.extensions["timeout"]["read"], 45.0)
            payload = json.loads(request.content)
            self.assertEqual(payload["model"], "muse-spark-1.3")
            content = payload["messages"][1]["content"]
            task = json.loads(content[0]["text"].split(": ", 1)[1])
            self.assertEqual(task, {key: inputs[key] for key in ("expected_visual", "server_action", "map")})
            self.assertTrue(content[1]["text"].startswith("BEFORE live frame metadata"))
            self.assertTrue(content[3]["text"].startswith("AFTER live frame metadata"))
            self.assert_frames(content, [inputs["before"], inputs["after"]])
            prompt = payload["messages"][0]["content"]
            for rule in ("SIMULATION action receipt", "unchanged vehicle position", "printed START", "cannot prove actual robot stopping", "untrusted"):
                self.assertIn(rule, prompt)
            self.assertTrue(payload["response_format"]["json_schema"]["strict"])
            return httpx.Response(200, json=envelope(action_result()))

        result = await self.provider(handler).action(inputs)
        self.assertEqual(result, action_result())
        self.assertEqual(inputs, original)
        self.assertEqual(len(calls), 1)

    async def test_signal_sends_specific_target_approach_stop_binding_and_original_frame(self):
        inputs = signal_inputs()

        def handler(request):
            payload = json.loads(request.content)
            content = payload["messages"][1]["content"]
            task = json.loads(content[0]["text"].split(": ", 1)[1])
            self.assertEqual(task, {key: inputs[key] for key in ("map", "signal_target", "server_stop")})
            self.assertEqual(task["server_stop"]["request_id"], "request-1")
            self.assertEqual(task["signal_target"]["pixel_polygon"], inputs["signal_target"]["pixel_polygon"])
            self.assert_frames(content, [inputs["frame"]])
            prompt = payload["messages"][0]["content"]
            for rule in ("mandatory SIMULATED stop", "no independent local color classifier", "Printed", "another approach",
                         "UNKNOWN and visible false", "multiple plausible targets", "not exposure time", "untrusted"):
                # Capitalization is immaterial to the transmitted rule.
                self.assertIn(rule.lower(), prompt.lower())
            schema = payload["response_format"]["json_schema"]["schema"]
            self.assertFalse(schema["additionalProperties"])
            self.assertEqual(set(schema["properties"]), {"color", "visible", "summary", "limitations"})
            return httpx.Response(200, json=envelope(signal_result("GREEN")))

        self.assertEqual(await self.provider(handler).signal(inputs), signal_result("GREEN"))

    async def test_all_action_verdicts_are_returned_without_inventing_a_decision(self):
        for verdict in ("PASS", "FAIL", "REOBSERVE", "UNKNOWN"):
            with self.subTest(verdict=verdict):
                result = action_result()
                result["verdict"] = verdict
                provider = self.provider(lambda _request: httpx.Response(200, json=envelope(result)))
                self.assertEqual(await provider.action(action_inputs()), result)

    async def test_all_signal_colors_are_returned_for_local_supervision(self):
        for color in ("RED", "GREEN", "UNKNOWN"):
            with self.subTest(color=color):
                result = signal_result(color)
                provider = self.provider(lambda _request: httpx.Response(200, json=envelope(result)))
                self.assertEqual(await provider.signal(signal_inputs()), result)

    async def test_signal_schema_rejects_unsafe_or_malformed_color_visibility_pairs(self):
        cases = []
        for key, value in (
            ("color", "YELLOW"), ("color", ["GREEN"]), ("visible", 1), ("visible", False),
            ("summary", " "), ("summary", "a" * 801), ("summary", " " * 800 + "a"),
            ("limitations", ["a"] * 9), ("limitations", ["a" * 301]), ("limitations", [None]),
        ):
            result = signal_result("GREEN")
            result[key] = value
            cases.append(result)
        unknown = signal_result("UNKNOWN")
        unknown["visible"] = True
        cases.append(unknown)
        extra = signal_result()
        extra["admit_crossing"] = True
        cases.append(extra)
        missing = signal_result()
        del missing["limitations"]
        cases.extend([missing, [], None])
        for index, result in enumerate(cases):
            with self.subTest(case=index):
                provider = self.provider(lambda _request: httpx.Response(200, json=envelope(result)))
                with self.assertRaises(SceneError) as raised:
                    await provider.signal(signal_inputs())
                self.assertEqual(raised.exception.code, "MUSE_SCHEMA")

    async def test_live_action_reuses_contract_with_strict_type_and_length_guards(self):
        cases = []
        for key, value in (
            ("verdict", []), ("verdict", "APPROVED"), ("observed", None), ("summary", " "),
            ("summary", "a" * 801), ("summary", " " * 800 + "a"), ("limitations", ["a"] * 9),
            ("limitations", ["a" * 301]), ("limitations", [False]),
        ):
            result = action_result()
            result[key] = value
            cases.append(result)
        extra = action_result()
        extra["robot_command"] = "private raw command"
        cases.extend([extra, None, []])
        for index, result in enumerate(cases):
            with self.subTest(case=index):
                provider = self.provider(lambda _request: httpx.Response(200, json=envelope(result)))
                with self.assertRaises(SceneError) as raised:
                    await provider.action(action_inputs())
                self.assertEqual(raised.exception.code, "MUSE_SCHEMA")

    async def test_refusal_truncation_bad_envelopes_and_json_are_sanitized(self):
        responses = [
            envelope(signal_result(), refusal="private raw refusal"), envelope(signal_result(), finish="length"),
            envelope(signal_result(), finish=None), {"choices": []}, {"choices": [{"message": None, "finish_reason": "stop"}]},
            {"choices": [{"finish_reason": "stop", "message": {"content": "private raw provider text"}}]},
        ]
        for response in responses:
            for method, inputs in (("action", action_inputs()), ("signal", signal_inputs())):
                with self.subTest(response=response, method=method):
                    provider = self.provider(lambda _request: httpx.Response(200, json=response))
                    with self.assertRaises(SceneError) as raised:
                        await getattr(provider, method)(inputs)
                    self.assertEqual(raised.exception.status_code, 502)
                    self.assertNotIn("private raw", str(raised.exception))
                    self.assertNotIn("test-only-not-a-secret", str(raised.exception))

    async def test_http_failure_and_redirect_are_not_retried_or_followed(self):
        for status in (302, 401, 429, 503):
            calls = []

            def handler(request):
                calls.append(request)
                return httpx.Response(status, text="private raw upstream", headers={"location": "https://example.org/redirect"})

            with self.subTest(status=status):
                with self.assertRaises(SceneError) as raised:
                    await self.provider(handler).signal(signal_inputs())
                self.assertEqual(raised.exception.code, "MUSE_REJECTED")
                self.assertNotIn("private raw", str(raised.exception))
                self.assertEqual(len(calls), 1)

    async def test_transport_failure_is_sanitized_for_both_methods(self):
        def timeout(request):
            raise httpx.ReadTimeout("private raw timeout", request=request)

        for method, inputs in (("action", action_inputs()), ("signal", signal_inputs())):
            with self.subTest(method=method), self.assertRaises(SceneError) as raised:
                await getattr(self.provider(timeout), method)(inputs)
            self.assertEqual(raised.exception.code, "MUSE_FAILED")
            self.assertNotIn("private raw", str(raised.exception))

    async def test_stream_size_is_bounded_before_reading_all_response_chunks(self):
        class OversizedStream(httpx.AsyncByteStream):
            chunks = 0

            async def __aiter__(self):
                for _index in range(20):
                    self.chunks += 1
                    yield b"x" * 100_001

        stream = OversizedStream()
        provider = self.provider(lambda _request: httpx.Response(200, stream=stream))
        with self.assertRaises(SceneError) as raised:
            await provider.signal(signal_inputs())
        self.assertEqual(raised.exception.code, "MUSE_RESPONSE_SIZE")
        self.assertEqual(stream.chunks, 10)

    async def test_invalid_inputs_are_rejected_before_dispatch(self):
        def unexpected(_request):
            raise AssertionError("Invalid task data must not be sent to a provider.")

        cases = []
        for frame_value in ({}, {"metadata": {}, "data": b"PNG"}, {"metadata": [], "data": frame_fixture()["data"]}):
            inputs = signal_inputs()
            inputs["frame"] = frame_value
            cases.append(("signal", inputs))
        mismatched = signal_inputs()
        mismatched["frame"]["metadata"]["sha256"] = "wrong"
        cases.append(("signal", mismatched))
        incomplete = signal_inputs()
        del incomplete["server_stop"]
        cases.append(("signal", incomplete))
        invalid_stop = signal_inputs()
        invalid_stop["server_stop"] = None
        cases.append(("signal", invalid_stop))
        huge = signal_inputs()
        huge["signal_target"]["description"] = "x" * 1_000_001
        cases.append(("signal", huge))
        nonfinite = signal_inputs()
        nonfinite["map"]["x"] = float("nan")
        cases.append(("signal", nonfinite))
        invalid_action = action_inputs()
        invalid_action["expected_visual"] = " "
        cases.append(("action", invalid_action))
        oversized_frame = action_inputs()
        oversized_frame["after"]["data"] = b"\xff\xd8" + b"x" * (8 * 1024 * 1024) + b"\xff\xd9"
        cases.append(("action", oversized_frame))
        for index, (method, inputs) in enumerate(cases):
            with self.subTest(case=index), self.assertRaises(SceneError) as raised:
                await getattr(self.provider(unexpected), method)(inputs)
            self.assertEqual(raised.exception.status_code, 422)

    async def test_missing_configuration_never_dispatches(self):
        def unexpected(_request):
            raise AssertionError("A key is required before dispatch.")

        for method, inputs in (("action", action_inputs()), ("signal", signal_inputs())):
            with self.subTest(method=method), self.assertRaises(SceneError) as raised:
                provider = MetaLiveReviewProvider("", transport=httpx.MockTransport(unexpected))
                await getattr(provider, method)(inputs)
            self.assertEqual(raised.exception.code, "MUSE_NOT_CONFIGURED")

    def test_signal_validation_returns_a_defensive_copy(self):
        original = signal_result()
        validated = validate_signal_result(original)
        validated["limitations"].append("Another limitation.")
        self.assertEqual(original, signal_result())


if __name__ == "__main__":
    unittest.main()
