"""Test the opt-in connectivity checker with fixtures only; never call Meta."""
from __future__ import annotations

from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error


SPEC = importlib.util.spec_from_file_location("check_muse_api", Path(__file__).resolve().parents[1] / "tools/check_muse_api.py")
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)
FIXTURE_KEY = "fixture-key-not-real"


class FakeResponse(io.BytesIO):
    status = 200

    def __init__(self, payload):
        super().__init__(json.dumps(payload).encode())


class FakeOpener:
    def __init__(self, *payloads):
        self.payloads = list(payloads)
        self.requests = []

    def open(self, request, *, timeout):
        self.requests.append(request)
        return FakeResponse(self.payloads.pop(0))


class MuseConnectionCheckTests(unittest.TestCase):
    def test_key_file_handles_quotes_and_rejects_ambiguous_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            for quote in ("", "'", '"'):
                path.write_text(f"\ufeff# Local fixture\nOTHER=value\nMETA_API_KEY={quote}{FIXTURE_KEY}{quote}\n", encoding="utf-8")
                self.assertEqual(checker.load_key(path), FIXTURE_KEY)
            for content in ("", "META_API_KEY=\n", "META_API_KEY=first\nMETA_API_KEY=second\n", "META_API_KEY=two words\n"):
                path.write_text(content, encoding="utf-8")
                with self.assertRaises(ValueError):
                    checker.load_key(path)

    def test_unavailable_model_never_sends_inference(self):
        opener = FakeOpener({"data": [{"id": "unrelated-fixture-model"}]})
        result = checker.run_check(opener, FIXTURE_KEY)
        self.assertEqual(result["status"], "model_unavailable")
        self.assertFalse(result["inference_sent"])
        self.assertEqual(len(opener.requests), 1)

    def test_success_requires_exact_ack_and_bounds_the_request(self):
        for reply, expected_status in ((checker.EXPECTED, "passed"), ("different reply", "unexpected_response")):
            opener = FakeOpener(
                {"data": [{"id": checker.MODELS[0]}]},
                {"choices": [{"message": {"content": reply}, "finish_reason": "stop"}], "usage": {"total_tokens": 20}},
            )
            result = checker.run_check(opener, FIXTURE_KEY)
            self.assertEqual(result["status"], expected_status)
            self.assertEqual(len(opener.requests), 2)
            request = opener.requests[1]
            self.assertEqual(request.full_url, "https://api.meta.ai/v1/chat/completions")
            self.assertEqual(request.get_header("Authorization"), "Bearer " + FIXTURE_KEY)
            body = json.loads(request.data)
            self.assertEqual(body["max_completion_tokens"], 128)
            self.assertNotIn(FIXTURE_KEY, request.data.decode())
            self.assertNotIn(FIXTURE_KEY, json.dumps(result))

    def test_error_reporting_redacts_provider_echoed_credential(self):
        body = io.BytesIO(json.dumps({"error": {"message": "Fixture rejection: " + FIXTURE_KEY}}).encode())
        error = urllib.error.HTTPError(checker.BASE_URL, 401, "Unauthorized", {}, body)
        output = io.StringIO()
        with patch.object(checker, "load_key", return_value=FIXTURE_KEY), patch.object(checker, "run_check", side_effect=error), redirect_stdout(output):
            self.assertEqual(checker.main(), 1)
        self.assertNotIn(FIXTURE_KEY, output.getvalue())
        report = json.loads(output.getvalue())
        self.assertEqual(report["http_status"], 401)
        self.assertIn("[REDACTED]", report["provider_message"])


if __name__ == "__main__":
    unittest.main()
