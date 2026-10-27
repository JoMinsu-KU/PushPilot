"""Private, crash-durable command journal. Incomplete dispatches are never replayed."""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3
import threading
import time


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


class ControlError(RuntimeError):
    def __init__(self, code, message, status=409):
        super().__init__(message)
        self.code, self.status = code, status


ACTIVE = {"queued", "waiting_observation", "dispatching", "committed", "running", "awaiting_review", "outcome_unknown"}


class Journal:
    def __init__(self, path: Path, clock=time.time):
        self.path, self.clock, self.lock = Path(path), clock, threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, check_same_thread=False, timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL;
            CREATE TABLE IF NOT EXISTS control_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS robot_commands(
                id TEXT PRIMARY KEY, digest TEXT NOT NULL, payload TEXT NOT NULL,
                state TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL,
                expires REAL NOT NULL, result TEXT, error TEXT, cancel_requested INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS robot_events(
                id INTEGER PRIMARY KEY AUTOINCREMENT, command_id TEXT, kind TEXT NOT NULL,
                created REAL NOT NULL, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS robot_observations(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS robot_reviews(id TEXT PRIMARY KEY, command_id TEXT NOT NULL, payload TEXT NOT NULL);
        """)

    @contextmanager
    def transaction(self):
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                yield
                self.db.commit()
            except BaseException:
                self.db.rollback()
                raise

    def event(self, command_id, kind, data):
        with self.transaction():
            self._event(command_id, kind, data)

    def _event(self, command_id, kind, data):
        self.db.execute("INSERT INTO robot_events(command_id,kind,created,data) VALUES(?,?,?,?)",
                        (command_id, kind, self.clock(), encode(data)))

    def get_meta(self, key, default=None):
        with self.lock:
            row = self.db.execute("SELECT value FROM control_meta WHERE key=?", (key,)).fetchone()
            return json.loads(row[0]) if row else deepcopy(default)

    def _meta(self, key, value):
        self.db.execute("INSERT INTO control_meta VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, encode(value)))

    def set_meta(self, key, value):
        with self.transaction():
            self._meta(key, value)

    def recover(self):
        with self.transaction():
            self._meta("armed", False)
            self.db.execute("UPDATE robot_commands SET state='interrupted_before_dispatch',error='Restart before publication; not replayed',updated=? WHERE state IN ('queued','waiting_observation')", (self.clock(),))
            self.db.execute("UPDATE robot_commands SET state='outcome_unknown',error='Process interrupted during dispatch; reconcile before continuing',updated=? WHERE state IN ('dispatching','committed','running')", (self.clock(),))
            self._event(None, "service_started_disarmed", {"automatic_replay": False})

    def get(self, request_id):
        with self.lock:
            row = self.db.execute("SELECT * FROM robot_commands WHERE id=?", (str(request_id),)).fetchone()
            if row is None:
                raise ControlError("NOT_FOUND", "Command not found.", 404)
            value = dict(row)
            for key in ("payload", "result"):
                value[key] = json.loads(value[key]) if value[key] else None
            value["cancel_requested"] = bool(value["cancel_requested"])
            return value

    def active(self):
        with self.lock:
            placeholders = ",".join("?" for _ in ACTIVE)
            rows = self.db.execute(f"SELECT id FROM robot_commands WHERE state IN ({placeholders}) ORDER BY created,id", tuple(ACTIVE)).fetchall()
            return [self.get(row[0]) for row in rows]

    def create(self, payload):
        raw = encode(payload)
        digest = hashlib.sha256(raw.encode()).hexdigest()
        request_id, now = str(payload["request_id"]), self.clock()
        with self.transaction():
            old = self.db.execute("SELECT digest FROM robot_commands WHERE id=?", (request_id,)).fetchone()
            if old:
                if old[0] != digest:
                    raise ControlError("IDEMPOTENCY_CONFLICT", "Request ID already binds a different command.")
                return self.get(request_id), False
            if self.active():
                raise ControlError("COMMAND_ACTIVE", "Finish, review or reconcile the current command first.")
            self.db.execute("INSERT INTO robot_commands(id,digest,payload,state,created,updated,expires) VALUES(?,?,?,'queued',?,?,?)",
                            (request_id, digest, raw, now, now, now + payload["admission_timeout_seconds"]))
            self._event(request_id, "command_created", {"digest": digest})
        return self.get(request_id), True

    def update(self, request_id, state, *, result=None, error=None):
        with self.transaction():
            self.db.execute("UPDATE robot_commands SET state=?,updated=?,result=COALESCE(?,result),error=? WHERE id=?",
                            (state, self.clock(), encode(result) if result is not None else None, error, str(request_id)))
            self._event(str(request_id), state, {"error": error})

    def observation(self, value):
        key, raw = str(value["observation_id"]), encode(value)
        with self.transaction():
            old = self.db.execute("SELECT payload FROM robot_observations WHERE id=?", (key,)).fetchone()
            if old and old[0] != raw:
                raise ControlError("OBSERVATION_CONFLICT", "Observation identity cannot be reused for different content.")
            self.db.execute("INSERT OR IGNORE INTO robot_observations VALUES(?,?)", (key, raw))
            self._meta("latest_observation_id", key)
        return value

    def get_observation(self, key=None):
        with self.lock:
            key = key or self.get_meta("latest_observation_id")
            row = self.db.execute("SELECT payload FROM robot_observations WHERE id=?", (str(key),)).fetchone()
            return json.loads(row[0]) if row else None

    def events(self, after=0):
        with self.lock:
            return [{**dict(row), "data": json.loads(row["data"])} for row in self.db.execute(
                "SELECT * FROM robot_events WHERE id>? ORDER BY id LIMIT 200", (after,))]

    def close(self):
        with self.lock:
            self.db.close()
