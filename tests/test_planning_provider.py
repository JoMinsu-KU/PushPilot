"""Offline MUSE route transport and trust-boundary tests with synthetic JPEGs."""
from __future__ import annotations

import base64
from copy import deepcopy
import hashlib
import json
import unittest

import cv2
import httpx
import numpy as np

from backend.meta import ProviderError
from backend.planning_provider import MetaPlanningProvider, validate_result


def image_fixture() -> bytes:
    image = np.full((64, 96, 3), 230, dtype=np.uint8)
    cv2.rectangle(image, (6, 28), (86, 42), (50, 50, 50), -1)
    success, data = cv2.imencode(".jpg", image)
    assert success
    return data.tobytes()


def context_fixture() -> dict:
    return {
        "map": {
            "id": "test-town", "version": "2", "geometry_hash": "d" * 64,
            "start": "SHOP", "start_heading": "east",
            "destinations": [{"id": "SCHOOL", "label": "School"}, {"id": "PARK", "label": "Park"}],
            "nodes": [
                {"id": "SHOP", "x_mm": 40, "y_mm": 50},
                {"id": "WEST", "x_mm": 10, "y_mm": 50},
                {"id": "SCHOOL", "x_mm": 10, "y_mm": 80},
                {"id": "PARK", "x_mm": 80, "y_mm": 50},
            ],
            "edges": [
                {"from": "SHOP", "to": "WEST", "bidirectional": True},
                {"from": "WEST", "to": "SCHOOL", "bidirectional": True},
                {"from": "SHOP", "to": "PARK", "bidirectional": True},
            ],
        },
        "frame": {"id": "f" * 32, "sha256": hashlib.sha256(image_fixture()).hexdigest(), "source": "live_preview"},
        "registration": {"id": "r" * 32, "status": "locked", "homography": [[1, 0, 0], [0, 1, 0], [0, 0, 1]]},
    }


def proposal() -> dict:
    return {
        "destination": "SCHOOL", "summary": "Use the road on the left side of the map to School.",
        "route_nodes": ["SHOP", "WEST", "SCHOOL"], "requires_clarification": False,
        "constraints": {"departure": "west", "first_turn": "any", "via_nodes": [], "avoid_nodes": []},
        "scene_assessment": {"status": "clear", "detail": "Roads are visible. Physical vehicle position is not established."},
    }


def envelope(result: dict | None = None, *, reason="stop", refusal=None) -> dict:
    return {"choices": [{"finish_reason": reason, "message": {
        "content": json.dumps(result if result is not None else proposal()), "refusal": refusal,
    }}]}


class PlanningProviderTests(unittest.TestCase):
    def provider(self, handler):
        return MetaPlanningProvider("test-only-not-a-secret", transport=httpx.MockTransport(handler))

    def test_original_jpeg_and_bound_graph_are_sent_without_pixel_transformation(self):
        original, context = image_fixture(), context_fixture()
        before = deepcopy(context)
        requests = []

        def handle(request):
            requests.append(request)
            self.assertEqual(str(request.url), MetaPlanningProvider.endpoint)
            self.assertEqual(request.headers["authorization"], "Bearer test-only-not-a-secret")
            self.assertEqual(request.extensions["timeout"]["connect"], 5.0)
            self.assertEqual(request.extensions["timeout"]["read"], 45.0)
            body = json.loads(request.content)
            self.assertEqual(body["model"], "muse-spark-1.3")
            user = body["messages"][1]["content"]
            self.assertEqual(user[0]["text"], "Operator goal (task data): Take the map's left road to School.")
            transmitted = json.loads(user[1]["text"].split(": ", 1)[1])
            self.assertEqual(transmitted, context)
            data_uri = user[2]["image_url"]["url"]
            self.assertTrue(data_uri.startswith("data:image/jpeg;base64,"))
            decoded = base64.b64decode(data_uri.split(",", 1)[1])
            self.assertEqual(decoded, original)
            self.assertEqual(hashlib.sha256(decoded).hexdigest(), context["frame"]["sha256"])
            schema = body["response_format"]["json_schema"]
            self.assertTrue(schema["strict"])
            self.assertEqual(set(schema["schema"]["properties"]["destination"]["enum"]), {"SCHOOL", "PARK", "UNKNOWN"})
            self.assertNotIn("PIZZA", json.dumps(schema))
            system = body["messages"][0]["content"]
            for rule in ("untrusted task", "Turn left/right/straight", "green signal", "never authorizes", "measured car pose",
                         "destination-only goal", "most direct connected road path", "Do not silently replace a requested route"):
                self.assertIn(rule, system)
            return httpx.Response(200, json=envelope())

        result = self.provider(handle).plan("Take the map's left road to School.", context, original)
        self.assertEqual(result, proposal())
        self.assertEqual(context, before)
        self.assertEqual(len(requests), 1)

    def test_unknown_and_known_destination_clarifications_have_no_route(self):
        for destination in ("UNKNOWN", "SCHOOL"):
            with self.subTest(destination=destination):
                result = proposal()
                result.update(destination=destination, requires_clarification=True, route_nodes=[])
                provider = self.provider(lambda _request: httpx.Response(200, json=envelope(result)))
                self.assertEqual(provider.plan("Which left?", context_fixture(), image_fixture()), result)

    def test_replaced_map_destination_strings_and_constraints_are_supported(self):
        context = context_fixture()
        context["map"]["destinations"] = ["SCHOOL", "PARK"]
        result = proposal()
        result["constraints"].update(first_turn="left", via_nodes=["WEST"], avoid_nodes=["PARK"])
        provider = self.provider(lambda _request: httpx.Response(200, json=envelope(result)))
        self.assertEqual(provider.plan("Via the western junction, avoid Park.", context, image_fixture()), result)

    def test_malformed_results_are_rejected_even_when_upstream_claims_strict_schema(self):
        cases = []
        for key, value in (
            ("destination", "NOWHERE"), ("destination", ["SCHOOL"]), ("summary", ""),
            ("summary", "  "), ("summary", "x" * 501), ("summary", " " * 500 + "a"),
            ("requires_clarification", 0), ("route_nodes", []),
            ("route_nodes", ["SHOP", "NOWHERE", "SCHOOL"]), ("route_nodes", "SHOP,SCHOOL"),
            ("route_nodes", ["SHOP", "PARK"]), ("route_nodes", ["SHOP", "WEST", "SHOP", "SCHOOL"]),
            ("route_nodes", ["SHOP", ["SCHOOL"]]), ("route_nodes", ["SHOP"] * 501),
            ("constraints", {}), ("scene_assessment", None),
        ):
            result = proposal()
            result[key] = value
            cases.append(result)
        for key, value in (
            ("departure", "camera-left"), ("first_turn", "west"), ("via_nodes", ["UNKNOWN"]),
            ("avoid_nodes", "PARK"), ("avoid_nodes", ["PARK", "PARK"]), ("first_turn", []),
        ):
            result = proposal()
            result["constraints"][key] = value
            cases.append(result)
        for key, value in (("status", "safe"), ("status", {}), ("detail", ""), ("detail", "x" * 1001)):
            result = proposal()
            result["scene_assessment"][key] = value
            cases.append(result)
        result = proposal()
        result["requires_clarification"] = True
        cases.append(result)
        result = proposal()
        result["destination"] = "UNKNOWN"
        cases.append(result)
        for location in (None, "constraints", "scene_assessment"):
            result = proposal()
            (result if location is None else result[location])["robot_command"] = "ignored raw payload"
            cases.append(result)
        result = proposal()
        del result["constraints"]
        cases.append(result)
        cases.extend(([], None, 42))
        for index, result in enumerate(cases):
            with self.subTest(case=index):
                provider = self.provider(lambda _request: httpx.Response(200, json=envelope(result) if result is not None else {
                    "choices": [{"finish_reason": "stop", "message": {"content": "null"}}],
                }))
                with self.assertRaises(ProviderError):
                    provider.plan("School", context_fixture(), image_fixture())

    def test_refusal_incomplete_envelope_and_json_fail_without_raw_error_disclosure(self):
        responses = [
            envelope(refusal="private raw refusal"), envelope(reason="length"), envelope(reason=None),
            {"choices": []}, {"choices": [{"message": {"content": "private raw invalid JSON"}, "finish_reason": "stop"}]},
            {"choices": [{"message": None, "finish_reason": "stop"}]},
            {"choices": [{"message": {"content": proposal()}, "finish_reason": "stop"}]},
        ]
        for response in responses:
            with self.subTest(response=response):
                provider = self.provider(lambda _request: httpx.Response(200, json=response))
                with self.assertRaises(ProviderError) as raised:
                    provider.plan("School", context_fixture(), image_fixture())
                self.assertNotIn("private raw", str(raised.exception))
                self.assertNotIn("test-only-not-a-secret", str(raised.exception))

    def test_http_rejection_redirect_and_timeout_never_fall_back_or_retry(self):
        for status in (302, 401, 429, 503):
            calls = []

            def reject(request):
                calls.append(request)
                return httpx.Response(status, text="private raw provider failure", headers={"Location": "https://example.org/redirect"})

            with self.subTest(status=status), self.assertRaises(ProviderError) as raised:
                self.provider(reject).plan("School", context_fixture(), image_fixture())
            self.assertEqual(len(calls), 1)
            self.assertNotIn("private raw", str(raised.exception))

        def timeout(request):
            raise httpx.ReadTimeout("private raw timeout", request=request)

        with self.assertRaises(ProviderError) as raised:
            self.provider(timeout).plan("School", context_fixture(), image_fixture())
        self.assertNotIn("private raw", str(raised.exception))

    def test_response_is_bounded_while_streaming(self):
        class OversizedStream(httpx.SyncByteStream):
            chunks = 0

            def __iter__(self):
                for _index in range(20):
                    self.chunks += 1
                    yield b"x" * 100_001

        stream = OversizedStream()
        provider = self.provider(lambda _request: httpx.Response(200, stream=stream))
        with self.assertRaisesRegex(ProviderError, "oversized"):
            provider.plan("School", context_fixture(), image_fixture())
        self.assertEqual(stream.chunks, 10)

    def test_invalid_input_is_rejected_before_dispatch(self):
        def unexpected(_request):
            raise AssertionError("Invalid inputs must not leave the backend.")

        provider = self.provider(unexpected)
        cases = [
            ("", context_fixture(), image_fixture()), ("x" * 2001, context_fixture(), image_fixture()),
            ("School", context_fixture(), b"not JPEG"), ("School", context_fixture(), bytearray(image_fixture())),
            ("School", context_fixture(), b"\xff\xd8" + b"x" * (8 * 1024 * 1024) + b"\xff\xd9"),
            ("School", {}, image_fixture()),
        ]
        duplicate = context_fixture()
        duplicate["map"]["nodes"].append(deepcopy(duplicate["map"]["nodes"][0]))
        cases.append(("School", duplicate, image_fixture()))
        oversized = context_fixture()
        oversized["untrusted_label"] = "x" * 1_000_001
        cases.append(("School", oversized, image_fixture()))
        nonfinite = context_fixture()
        nonfinite["frame"]["age_ms"] = float("nan")
        cases.append(("School", nonfinite, image_fixture()))
        for index, args in enumerate(cases):
            with self.subTest(case=index), self.assertRaises(ProviderError):
                provider.plan(*args)
        with self.assertRaisesRegex(ProviderError, "not configured"):
            MetaPlanningProvider("", transport=httpx.MockTransport(unexpected)).plan("School", context_fixture(), image_fixture())

    def test_validation_returns_a_defensive_copy(self):
        output = proposal()
        validated = validate_result(output, context_fixture())
        validated["route_nodes"].append("PARK")
        validated["constraints"]["via_nodes"].append("WEST")
        self.assertEqual(output, proposal())


if __name__ == "__main__":
    unittest.main()
