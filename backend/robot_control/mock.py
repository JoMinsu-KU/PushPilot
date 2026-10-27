"""Equipment-free receiver double. Every result is explicitly simulation-only."""
from copy import deepcopy
import threading
import time
from uuid import uuid4


class MockReceiver:
    def __init__(self):
        self.lock = threading.RLock()
        self.calls = []
        self.delay = 0
        self.failure = None
        self.state = {"connected": True, "idle": True, "stage": "idle", "session_id": uuid4().hex,
                      "seq": 1, "profile_id": "mock-profile", "actual_pose": [0., 0., 100., 180., 0., 0.],
                      "actual_joint": [0.] * 6, "physical_execution": True,
                      "profile": {"tcp_id": "mock-tcp", "allow_motion": True, "site_verified": True,
                                  "translation_speed_mm_s": 5, "translation_accel_mm_s2": 10}, "reason": None}

    def open(self):
        pass

    def close(self):
        pass

    def snapshot(self):
        with self.lock:
            return deepcopy(self.state)

    def reconcile(self, expected_receiver):
        with self.lock:
            if not self.state["idle"] or any(self.state[key] != expected_receiver[key] for key in ("session_id", "seq", "profile_id")):
                raise ValueError("Mock receiver is not bound idle.")
            return {"reconciled": True, "source": "mock", "physical_execution": False, **expected_receiver}

    def execute(self, command, on_event):
        wire = {"request_id": uuid4().hex, "session_id": self.state["session_id"],
                "seq": self.state["seq"], "profile_id": self.state["profile_id"], "command_digest": "mock-digest"}
        on_event("publication_intent", {"wire_command": wire})
        with self.lock:
            self.calls.append(deepcopy(command))
            self.state.update(idle=False, stage="moving")
        on_event("published", wire)
        if self.delay:
            time.sleep(self.delay)
        if self.failure:
            raise self.failure
        with self.lock:
            if command["target"] is not None and command["kind"] in {"translate", "rotate"}:
                self.state["actual_pose"] = command["target"][:]
            if command["kind"] == "profile_update":
                self.state["profile"] = deepcopy(command["profile"])
                self.state["profile_id"] = uuid4().hex
            self.state.update(seq=self.state["seq"] + 1, idle=True, stage="idle")
        result = {"kind": "mock_endpoint_verified", "data": {**wire, "actual_pose": self.state["actual_pose"][:]},
                  "source": "mock", "physical_execution": False}
        on_event("verified", result)
        return result
