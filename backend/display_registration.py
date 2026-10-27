"""Private receipts for explicitly resuming a previously locked drawing view."""
from __future__ import annotations

import json

from backend.scene import SceneError


class DisplayRegistrationService:
    def __init__(self, store, camera):
        self.store, self.camera = store, camera
        with store._lock, store._db:
            store._db.execute("CREATE TABLE IF NOT EXISTS display_reference_receipts (id TEXT PRIMARY KEY, value TEXT NOT NULL)")

    def _remember(self, snapshot):
        reference_id = snapshot["registration"]["id"]
        self.store._db.execute("INSERT OR IGNORE INTO display_reference_receipts(id,value) VALUES(?,?)",
                               (reference_id, json.dumps(snapshot)))
        return snapshot

    def available(self):
        with self.store._lock:
            row = self.store._db.execute("SELECT value FROM display_reference_receipts ORDER BY rowid DESC LIMIT 1").fetchone()
            if not row:
                return False
            saved = json.loads(row["value"])
            current = self.camera.snapshot()
            keys = ("map_id", "map_version", "map_hash", "camera_id", "epoch")
            return all(saved[key] == current[key] for key in keys)

    def register(self, epoch, frame_id):
        with self.store._lock, self.store._db:
            return self._remember(self.camera.register(epoch, frame_id))

    def resume(self, epoch):
        with self.store._lock, self.store._db:
            row = self.store._db.execute("SELECT value FROM display_reference_receipts ORDER BY rowid DESC LIMIT 1").fetchone()
            if not row:
                raise SceneError(409, "No prior server-held display reference exists. Lock a fresh four-marker view.", "LIVE_REFERENCE_MISSING")
            saved = json.loads(row["value"])
            if saved["epoch"] != epoch:
                raise SceneError(409, "The prior reference belongs to another camera epoch. Lock its current view explicitly.", "LIVE_REFERENCE_CHANGED")
            current = self.camera.snapshot()
            if (current["registration"]["id"] == saved["registration"]["id"]
                    and current["registration"]["status"] in {"locked", "locked_partial", "locked_occluded"}):
                return current
            return self._remember(self.camera.restore_reference(saved))
