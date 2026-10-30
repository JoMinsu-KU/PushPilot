"""Offline endpoint selection; preserves motion evidence and stage coordinates."""
from copy import deepcopy

from backend.robot_control.mission_catalog import content_hash


def select_delivery_endpoint(packet, route_code, step_id, *, reason, max_return_span_mm=150.):
    """Return a new packet with a terminal delivery check and bounded empty returns.

    No transport, activation, historical-verdict rewrite or arrival assertion.
    Return splitting reuses existing stage vertices, never invents a shortcut.
    """
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("Record the operator's endpoint selection.")
    if not 20 <= max_return_span_mm <= 180:
        raise ValueError("Retain margin below the existing 200 mm local profile cap.")
    result = deepcopy(packet)
    route = result["routes"][route_code]
    matches = [i for i, s in enumerate(route["steps"]) if s["id"] == step_id]
    if len(matches) != 1:
        raise ValueError("Select exactly one existing step.")
    index = matches[0]
    selected = route["steps"][index]
    returns = route["early_arrival_returns"].get(step_id)
    if (not selected.get("can_accept_early_arrival") or selected.get("signal_gate")
            or not returns):
        raise ValueError("A selected endpoint needs completed withdrawal and an empty return.")
    previous_route = deepcopy(route)
    route["steps"] = route["steps"][:index + 1]
    for step in route["steps"]:
        step["at_goal"] = step["id"] == step_id
    route["parking"]["mode"] = "delivery_only"
    terminal = result["primitives"][selected["primitive_id"]]
    if not terminal["target_tool_clear"] or terminal["stages"][-1]["phase"] != "withdraw":
        raise ValueError("Finish only after the contact unit's existing withdrawal.")
    source_context = terminal["target_context_id"]
    updated_returns = []
    for pid in returns:
        row = result["primitives"][pid]
        if row["source_context_id"] != source_context or not row["empty_tool"]:
            raise ValueError("Return must be an exactly connected empty-tool chain.")
        source_context = row["target_context_id"]
        if row["kind"] == "wrist_edge":
            updated_returns.append(pid)
            continue
        if any(s["phase"] != "empty" for s in row["stages"]):
            raise ValueError("Never split a loaded action as an empty return.")
        groups, group = [], []
        for stage in row["stages"]:
            if group and group[-1]["target_base"] != stage["start_base"]:
                raise ValueError("Return stages must be continuous.")
            candidate = group + [stage]
            points = [candidate[0]["start_base"]] + [s["target_base"] for s in candidate]
            span = max(max(p[i] for p in points) - min(p[i] for p in points) for i in range(3))
            if span > max_return_span_mm:
                if not group:
                    raise ValueError("One stage exceeds the local return bound.")
                groups.append(group)
                group = [stage]
            else:
                group = candidate
        groups.append(group)
        if len(groups) == 1:
            updated_returns.append(pid)
            continue
        prior = row["source_context_id"]
        for number, stages in enumerate(groups, 1):
            new_id = pid + "/bounded-" + str(number)
            target = row["target_context_id"] if number == len(groups) else new_id + "/end"
            new = deepcopy(row)
            new.update(id=new_id, stages=stages, source_context_id=prior, target_context_id=target,
                       original_verdict="MISSING", repeatability_qualified=False,
                       candidate_reason="Existing empty return split at existing vertices; no new contact or increased limits.")
            new["geometry_sha256"] = content_hash({"kind": new["kind"],
                "stages": [{k: s[k] for k in ("phase", "start_base", "target_base")} for s in stages],
                "contact_travel_limit_mm": new.get("contact_travel_limit_mm", 20.)})
            if new_id in result["primitives"]:
                raise ValueError("Endpoint revision IDs already exist; do not overwrite evidence.")
            result["primitives"][new_id] = new
            if target != row["target_context_id"]:
                context = deepcopy(result["contexts"][row["target_context_id"]])
                context.update(pose_base=stages[-1]["target_base"], tool_clear=True)
                result["contexts"][target] = context
            updated_returns.append(new_id)
            prior = target
    if source_context != route["start_context_id"]:
        raise ValueError("Empty return must restore the original START context.")
    route["empty_return"] = updated_returns
    route["early_arrival_returns"][step_id] = updated_returns
    route["counts"] = {"route_units": len(route["steps"]),
        "route_stages": sum(len(result["primitives"][s["primitive_id"]]["stages"]) for s in route["steps"]),
        "recontact_stages": sum(len(result["primitives"][s["signal_gate"]["recontact_primitive_id"]]["stages"])
                                for s in route["steps"] if s.get("signal_gate")),
        "return_stages": sum(len(result["primitives"][pid]["stages"]) for pid in updated_returns)}
    result.setdefault("endpoint_revisions", []).append({"route_code": route_code, "step_id": step_id,
        "reason": reason, "previous_route": previous_route, "motion_stages_preserved": True,
        "historical_reviews_rewritten": False, "arrival_requires_fresh_muse": True})
    result["geometry_manifest_sha256"] = content_hash({"primitives": result["primitives"],
        "routes": result["routes"], "contexts": result["contexts"],
        "posture_binding_sha256": result["posture_binding_sha256"]})
    return result
