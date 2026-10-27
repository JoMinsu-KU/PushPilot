"""Explicitly test Meta authentication and one tiny Muse Spark completion.

Reads the repository-local .env, never prints credentials, never follows redirects,
and never contacts a robot. No live calls are made when this module is imported.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import socket
import time
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "https://api.meta.ai/v1"
MODELS = ("muse-spark-1.3", "muse-spark-1.2", "muse-spark-1.1")
EXPECTED = "PUSHPILOT_API_OK"
MAX_RESPONSE_BYTES = 1_048_576


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Keep the bearer credential confined to the documented API origin."""

    def redirect_request(self, request, fp, code, message, headers, newurl):
        return None


def load_key(path: Path) -> str:
    """Read only the named key; accept a plain or single/double-quoted value."""
    values = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        name, separator, value = line.strip().partition("=")
        if separator and name.strip() == "META_API_KEY":
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            values.append(value)
    if len(values) != 1 or not values[0] or re.search(r"\s", values[0]):
        raise ValueError("Set exactly one nonempty META_API_KEY in the local .env.")
    return values[0]


def request_json(opener, key: str, path: str, payload=None):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        BASE_URL + path, data=body,
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
    )
    start = time.monotonic()
    with opener.open(request, timeout=45) as response:
        data = response.read(MAX_RESPONSE_BYTES + 1)
        if len(data) > MAX_RESPONSE_BYTES:
            raise ValueError("Provider response exceeded the connection-test limit.")
        return response.status, json.loads(data), round((time.monotonic() - start) * 1000)


def run_check(opener, key: str) -> dict:
    status, catalog, elapsed = request_json(opener, key, "/models")
    enabled = {item.get("id") for item in catalog["data"] if isinstance(item, dict)}
    model = next((name for name in MODELS if name in enabled), None)
    result = {"catalog_http_status": status, "catalog_latency_ms": elapsed}
    if model is None:
        return {**result, "status": "model_unavailable", "inference_sent": False}
    status, completion, elapsed = request_json(opener, key, "/chat/completions", {
        "model": model,
        "messages": [{"role": "user", "content": "Reply exactly: " + EXPECTED}],
        "reasoning_effort": "minimal",
        "max_completion_tokens": 128,
    })
    choice = completion["choices"][0]
    text = choice["message"]["content"]
    if not isinstance(text, str):
        raise ValueError("Provider returned no plain-text completion.")
    usage = completion.get("usage") or {}
    return {
        **result,
        "status": "passed" if text.strip() == EXPECTED else "unexpected_response",
        "requested_model": model,
        "completion_http_status": status,
        "completion_latency_ms": elapsed,
        "expected_reply_matched": text.strip() == EXPECTED,
        "reply": EXPECTED if text.strip() == EXPECTED else "[unexpected content omitted]",
        "finish_reason": choice.get("finish_reason"),
        "usage": {name: usage.get(name) for name in ("prompt_tokens", "completion_tokens", "total_tokens")},
        "inference_sent": True,
    }


def main() -> int:
    key = ""
    report = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "endpoint": BASE_URL,
        "credential_source": "repository-local .env / META_API_KEY",
        "robot_contacted": False,
        "image_inference_tested": False,
        "automatic_retries": 0,
    }
    try:
        key = load_key(ROOT / ".env")
        report.update(run_check(urllib.request.build_opener(NoRedirect()), key))
    except urllib.error.HTTPError as error:
        report.update(status="http_error", http_status=error.code)
        try:
            payload = json.loads(error.read(65_536))
            message = payload.get("error", {}).get("message")
            if isinstance(message, str):
                report["provider_message"] = message.replace(key, "[REDACTED]")[:500]
        except (ValueError, AttributeError, TypeError):
            pass
    except (urllib.error.URLError, TimeoutError, socket.timeout):
        report.update(status="network_error", detail="Network or TLS connection failed; credentials were not printed.")
    except (OSError, ValueError, KeyError, TypeError, IndexError) as error:
        report.update(status="configuration_or_protocol_error", error_type=type(error).__name__)
    serialized = json.dumps(report, indent=2)
    if key:
        serialized = serialized.replace(key, "[REDACTED]")
    print(serialized)
    return 0 if report.get("status") == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
