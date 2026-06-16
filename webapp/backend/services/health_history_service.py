"""
Health History Service (Mission Control — Phase 4)
==================================================
The shared time-series + events store behind Mission Control's history, uptime
%, response-time trends, the incident timeline, and the in-app Alerts view.
Everything reads from here; it is written on every probe run.

SQLite (stdlib) at logs/health_history.db, thread-safe (Flask is threaded and the
scheduler writes too). Three tables:

  sample(ts, project, target_id, name, role, kind, status, response_ms, vantage)
      one row per target (host or fabric item) per probe run — drives uptime %,
      the response-time trend, and the status sparkline.
  event(ts, project, target_id, name, from_status, to_status)
      a status TRANSITION (e.g. ok->crit) — drives the incident timeline.
  heartbeat(target_id PK, project, last_seen, source)
      per-host push heartbeats (dead-man's switch); silence is also derived from
      sample history (a previously-seen target now crit/na/unreachable).

NA samples are kept for completeness but excluded from the uptime denominator
(a check that can't run from here shouldn't count against uptime).
"""

import sqlite3
import threading
import time
from pathlib import Path

# Statuses that count as "down" for uptime + alerting. NA/unknown are excluded
# from the uptime denominator.
_DOWN = ("warn", "crit")
_COUNTABLE = ("ok", "warn", "crit")


class HealthHistoryService:
    def __init__(self, project_root: Path):
        self.db_path = project_root / "logs" / "health_history.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        with self._lock:
            self._conn.executescript("""
                CREATE TABLE IF NOT EXISTS sample(
                    ts INTEGER, project TEXT, target_id TEXT, name TEXT, role TEXT,
                    kind TEXT, status TEXT, response_ms INTEGER, vantage TEXT);
                CREATE INDEX IF NOT EXISTS idx_sample_pt ON sample(project, target_id, ts);
                CREATE INDEX IF NOT EXISTS idx_sample_ts ON sample(project, ts);
                CREATE TABLE IF NOT EXISTS event(
                    ts INTEGER, project TEXT, target_id TEXT, name TEXT,
                    from_status TEXT, to_status TEXT);
                CREATE INDEX IF NOT EXISTS idx_event_ts ON event(project, ts);
                CREATE TABLE IF NOT EXISTS heartbeat(
                    target_id TEXT PRIMARY KEY, project TEXT, last_seen INTEGER, source TEXT);
                CREATE TABLE IF NOT EXISTS ack(
                    id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER, project TEXT,
                    target_id TEXT, status TEXT, name TEXT, role TEXT, reason TEXT, cleared_by TEXT);
                CREATE INDEX IF NOT EXISTS idx_ack ON ack(project, target_id, status, ts);
            """)
            self._conn.commit()

    # ------------------------------------------------------------------
    # Write — called on every probe run (real + demo)
    # ------------------------------------------------------------------

    def record_run(self, project: str, payload: dict, vantage: str = "dashboard"):
        """Persist one sample per target and emit a status-transition event when
        a target's status changes vs. its previous sample."""
        now = int(time.time())
        rows = []
        for h in payload.get("hosts", []):
            rows.append((h.get("instance_id") or h.get("name"), h.get("name"),
                         h.get("role"), "host", h.get("status"), h.get("response_ms")))
        for f in payload.get("fabric", []):
            rows.append((f.get("id"), f.get("label"), f.get("kind"), "fabric",
                         f.get("status"), f.get("response_ms")))
        with self._lock:
            for tid, name, role, kind, status, rms in rows:
                if not tid or not status:
                    continue
                prev = self._conn.execute(
                    "SELECT status FROM sample WHERE project=? AND target_id=? "
                    "ORDER BY rowid DESC LIMIT 1", (project, tid)).fetchone()
                prev_status = prev["status"] if prev else None
                self._conn.execute(
                    "INSERT INTO sample(ts,project,target_id,name,role,kind,status,response_ms,vantage) "
                    "VALUES(?,?,?,?,?,?,?,?,?)",
                    (now, project, tid, name, role, kind, status, rms, vantage))
                if prev_status is not None and prev_status != status:
                    self._conn.execute(
                        "INSERT INTO event(ts,project,target_id,name,from_status,to_status) "
                        "VALUES(?,?,?,?,?,?)", (now, project, tid, name, prev_status, status))
            self._conn.commit()

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def series(self, project: str, target_id: str, window_secs: int = 86400, limit: int = 300):
        """Status + response-time samples for one target over a window (oldest→newest)."""
        since = int(time.time()) - window_secs
        with self._lock:
            rows = self._conn.execute(
                "SELECT ts,status,response_ms,vantage FROM sample "
                "WHERE project=? AND target_id=? AND ts>=? ORDER BY ts ASC LIMIT ?",
                (project, target_id, since, limit)).fetchall()
        return [dict(r) for r in rows]

    def uptime(self, project: str, target_id: str, window_secs: int = 86400) -> dict:
        """Uptime % over the window = ok / (ok+warn+crit). NA/unknown excluded."""
        since = int(time.time()) - window_secs
        with self._lock:
            rows = self._conn.execute(
                "SELECT status, COUNT(*) c FROM sample "
                "WHERE project=? AND target_id=? AND ts>=? GROUP BY status",
                (project, target_id, since)).fetchall()
        counts = {r["status"]: r["c"] for r in rows}
        denom = sum(counts.get(s, 0) for s in _COUNTABLE)
        ok = counts.get("ok", 0)
        pct = round(100.0 * ok / denom, 2) if denom else None
        return {"uptime_pct": pct, "samples": sum(counts.values()), "counted": denom,
                "ok": ok, "warn": counts.get("warn", 0), "crit": counts.get("crit", 0)}

    def events(self, project: str = None, window_secs: int = 604800, limit: int = 200):
        """Recent status transitions (incident timeline). All projects if project is None."""
        since = int(time.time()) - window_secs
        with self._lock:
            if project:
                rows = self._conn.execute(
                    "SELECT * FROM event WHERE project=? AND ts>=? ORDER BY ts DESC LIMIT ?",
                    (project, since, limit)).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM event WHERE ts>=? ORDER BY ts DESC LIMIT ?",
                    (since, limit)).fetchall()
        return [dict(r) for r in rows]

    def heartbeat(self, target_id: str, project: str, source: str = "push"):
        now = int(time.time())
        with self._lock:
            self._conn.execute(
                "INSERT INTO heartbeat(target_id,project,last_seen,source) VALUES(?,?,?,?) "
                "ON CONFLICT(target_id) DO UPDATE SET last_seen=?, project=?, source=?",
                (target_id, project, now, source, now, project, source))
            self._conn.commit()
        return now

    def stale_heartbeats(self, max_age_secs: int = 900):
        """Targets whose last heartbeat is older than max_age (dead-man's switch)."""
        cutoff = int(time.time()) - max_age_secs
        with self._lock:
            rows = self._conn.execute(
                "SELECT target_id, project, last_seen, source FROM heartbeat WHERE last_seen < ?",
                (cutoff,)).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Clear / archive alerts (acknowledgements)
    # ------------------------------------------------------------------

    def clear_alert(self, project, target_id, status, name=None, role=None,
                    reason=None, cleared_by=None):
        """Acknowledge ('clear') an alert → archive it. Suppresses the alert while
        the target stays in this status; it re-raises if the target later
        transitions back INTO a bad state (a fresh incident)."""
        now = int(time.time())
        with self._lock:
            self._conn.execute(
                "INSERT INTO ack(ts,project,target_id,status,name,role,reason,cleared_by) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (now, project, target_id, status, name, role, reason, cleared_by))
            self._conn.commit()
        return now

    def _entered_ts(self, project, target_id, status) -> int:
        """When the target most recently transitioned INTO `status` (0 if never —
        i.e. it's been in this state since first sample)."""
        with self._lock:
            row = self._conn.execute(
                "SELECT MAX(ts) t FROM event WHERE project=? AND target_id=? AND to_status=?",
                (project, target_id, status)).fetchone()
        return (row["t"] or 0) if row else 0

    def is_suppressed(self, project, target_id, status) -> bool:
        """True if this alert was cleared AND the target hasn't re-entered the bad
        state since (so a recurrence is NOT suppressed)."""
        with self._lock:
            row = self._conn.execute(
                "SELECT MAX(ts) t FROM ack WHERE project=? AND target_id=? AND status=?",
                (project, target_id, status)).fetchone()
        acked_ts = (row["t"] or 0) if row else 0
        if not acked_ts:
            return False
        return acked_ts >= self._entered_ts(project, target_id, status)

    def archived(self, project: str = None, limit: int = 200):
        """Cleared alerts (the archive), most recent first."""
        with self._lock:
            if project:
                rows = self._conn.execute(
                    "SELECT * FROM ack WHERE project=? ORDER BY ts DESC LIMIT ?",
                    (project, limit)).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM ack ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def latest_per_target(self, project: str):
        """Most recent sample for each target — used to compute current alerts.
        Keyed on MAX(rowid) (insertion order), not MAX(ts): ts is integer-seconds
        so rapid switches in the same second would tie and return stale rows."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT s.* FROM sample s JOIN (SELECT target_id, MAX(rowid) mr FROM sample "
                "WHERE project=? GROUP BY target_id) m ON s.rowid=m.mr",
                (project,)).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Demo seeding — so the demo's history/graphs/timeline aren't empty
    # ------------------------------------------------------------------

    def seed_demo(self, project: str = "demo"):
        """If the demo has no history, synthesize a believable ~24h series with a
        couple of incidents so the graphs + timeline have something to show."""
        with self._lock:
            existing = self._conn.execute(
                "SELECT COUNT(*) c FROM sample WHERE project=?", (project,)).fetchone()["c"]
        if existing:
            return False
        now = int(time.time())
        targets = [
            ("i-0demo-redirector-01", "redirector-01", "redirector", "host"),
            ("i-0demo-redirector-02", "redirector-02", "redirector", "host"),
            ("i-0demots01", "c2-teamserver-01", "teamserver", "host"),
            ("vpc_peering", "VPC peering", "fabric", "fabric"),
            ("domain", "demo-engagement.example.com", "dns", "fabric"),
        ]
        # 24h, one sample every 10 min = 144 points.
        step = 600
        points = 144
        with self._lock:
            for tid, name, role, kind in targets:
                prev = None
                for i in range(points):
                    ts = now - (points - i) * step
                    # Mostly healthy with two short redirector-02 blips.
                    status = "ok"
                    if tid == "i-0demo-redirector-02" and (30 <= i < 36 or 90 <= i < 94):
                        status = "warn"
                    rms = None
                    if role == "redirector":
                        rms = 120 + (i % 11) * 7 + (180 if status == "warn" else 0)
                    elif kind == "dns":
                        rms = 60 + (i % 9) * 5
                    self._conn.execute(
                        "INSERT INTO sample(ts,project,target_id,name,role,kind,status,response_ms,vantage) "
                        "VALUES(?,?,?,?,?,?,?,?,?)",
                        (ts, project, tid, name, role, kind, status, rms, "dashboard"))
                    if prev is not None and prev != status:
                        self._conn.execute(
                            "INSERT INTO event(ts,project,target_id,name,from_status,to_status) "
                            "VALUES(?,?,?,?,?,?)", (ts, project, tid, name, prev, status))
                    prev = status
            self._conn.commit()
        return True
