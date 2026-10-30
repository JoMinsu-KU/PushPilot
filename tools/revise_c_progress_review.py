"""Prepare an offline C-only observation-policy candidate; never activate it."""
from copy import deepcopy


def select_c_progress_review(config):
    result = deepcopy(config)
    if result.get("schema") == "pushpilot.site-trial-driver.v1":
        if result["workspace_bindings"].get("C", {}).get("destination") != "VILLA":
            raise ValueError("Bind the C Villa route before enabling its review policy.")
        modes = result["observations"].setdefault("route_review_modes", {})
        if not isinstance(modes, dict) or any(code != "C" for code in modes):
            raise ValueError("Unexpected review policy override.")
        modes["C"] = "intermediate_progress"
        return result, ["C: intermediate loaded steps only"]
    selected = []
    for route in result["routes"]:
        plan = route["plan"]
        if plan["destination"] != "VILLA":
            continue
        if plan["release_mode"] != "site_trial" or plan["parking"]["mode"] != "delivery_only" or plan.get("corrections"):
            raise ValueError("Only the current-site C delivery trial supports progress-only review.")
        for step in plan["steps"]:
            if not step["id"].startswith("C-step-"):
                raise ValueError("Unexpected C route step identity.")
            if step.get("at_goal") or step["primitive"].get("empty_tool"):
                continue
            step["review_mode"] = "intermediate_progress"
            selected.append(step["id"])
    if not selected:
        raise ValueError("No C intermediate loaded steps found.")
    return result, selected
