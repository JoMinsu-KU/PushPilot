"""Evaluate recorded-pair simulation reviews on three original synthetic cases.

Defaults to generating labelled fixtures only. --call-meta makes exactly three
explicit application API requests to Meta using the server's ignored .env key.
It never opens a camera, connects to a robot, or changes a running workspace.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.action_review_fixtures import EXPECTATION, write_fixtures


def evaluate(output: Path, *, call_meta: bool = False) -> dict:
    output = output.resolve()
    if output == ROOT or ROOT in output.parents:
        raise ValueError("Evaluation evidence must be outside the source repository.")
    output.mkdir(parents=True, exist_ok=False)
    fixtures = write_fixtures(output / "fixtures")
    report = {
        "schema_version": "pushpilot.synthetic-evaluation.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "input_kind": "original_synthetic_schematic",
        "physical_execution": False,
        "camera_connected": False,
        "actual_provider_requests": 0,
        "expected_visual": EXPECTATION,
        "fixtures": {name: {"file": str(path.relative_to(output)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                     for name, path in fixtures.items()},
        "cases": [],
        "limits": ["One designed case per condition, not a held-out accuracy evaluation.",
                   "No photographs, measured motion, signal detection or physical success are tested.",
                   "Token usage is provider-reported; prices and cost are not inferred."],
    }
    if call_meta:
        from fastapi.testclient import TestClient
        from backend.app import create_app
        from backend.settings import Settings

        key = Settings.from_environment().meta_api_key
        if not key:
            raise ValueError("META_API_KEY must be configured on the backend for --call-meta.")
        for name, expected_verdicts, expected_states in (
            ("success", ["PASS"], ["READY"]),
            ("no_progress", ["FAIL"], ["FAULT"]),
            ("occluded", ["REOBSERVE", "UNKNOWN"], ["REOBSERVE"]),
        ):
            directory = output / name
            settings = Settings(db_path=str(directory / "workspace.sqlite3"), meta_api_key=key)
            with TestClient(create_app(settings=settings)) as client:
                def command(endpoint: str, **extra):
                    revision = client.get("/api/v1/state").json()["revision"]
                    response = client.post(f"/api/v1/{endpoint}", json={
                        "request_id": str(uuid4()), "expected_revision": revision, **extra,
                    })
                    response.raise_for_status()
                    return response.json()

                def upload(path: Path):
                    response = client.post("/api/v1/scene/frames", files={"file": (path.name, path.read_bytes(), "image/png")})
                    response.raise_for_status()
                    return response.json()

                before = upload(fixtures["before"])
                plan = command("goals", text="Push the car from Pizza to the Bookstore.", provider="demo", source="typed")
                command("approve", plan_id=plan["plan"]["id"], plan_revision=plan["plan"]["revision"])
                pending = command("advance")
                after = upload(fixtures[name])
                report["actual_provider_requests"] += 1
                response = command("action-reviews", review_id=pending["review"]["id"],
                                   expected_scene_revision=after["revision"],
                                   before_frame_id=before["frame"]["id"], after_frame_id=after["frame"]["id"],
                                   expected_visual=EXPECTATION)
                review = response["review"]
                case = {"name": name, "expected_verdicts": expected_verdicts,
                        "expected_states": expected_states, "actual_verdict": review["verdict"],
                        "actual_state": response["state"], "review": review,
                        "matched_expected": review["verdict"] in expected_verdicts and response["state"] in expected_states}
                report["cases"].append(case)
                (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
                print(json.dumps({"case": name, "actual_verdict": case["actual_verdict"],
                                  "actual_state": case["actual_state"], "matched_expected": case["matched_expected"]}), flush=True)
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="New evidence directory outside the repository.")
    parser.add_argument("--call-meta", action="store_true", help="Send the three synthetic image pairs to the actual Meta API.")
    args = parser.parse_args()
    try:
        report = evaluate(args.output, call_meta=args.call_meta)
    except (OSError, ValueError) as error:
        print(f"Evaluation failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"output": str(args.output.resolve()), "actual_provider_requests": report["actual_provider_requests"],
                      "all_cases_matched": all(case["matched_expected"] for case in report["cases"]) if report["cases"] else None}))
    return 0 if all(case["matched_expected"] for case in report["cases"]) else 2


if __name__ == "__main__":
    raise SystemExit(main())
