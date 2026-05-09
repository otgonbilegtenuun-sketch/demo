"""
database.py — SQLite setup, queries, and demo seed data.
All tables use WAL mode for safe concurrent access from the camera thread.
"""

import os
import sqlite3
import threading
import random
import hashlib
import secrets
import base64
import hmac
from datetime import date, datetime
from typing import Optional
from log_setup import get_logger
log = get_logger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "classroom.db")
_thread_local = threading.local()


def get_db() -> sqlite3.Connection:
    """Return a per-thread SQLite connection (WAL mode, row factory)."""
    if not hasattr(_thread_local, "conn"):
        conn = sqlite3.connect(DB_PATH, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        _thread_local.conn = conn
    return _thread_local.conn


def init_db():
    """Create tables and seed demo data on first run."""
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS students (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT    NOT NULL,
            class_name    TEXT    DEFAULT 'Class A',
            role          TEXT    DEFAULT 'student',
            face_embedding BLOB,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS attendance (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id       INTEGER NOT NULL,
            date             TEXT    NOT NULL,
            arrived_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_seen        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            attention_frames INTEGER DEFAULT 0,
            total_frames     INTEGER DEFAULT 0,
            UNIQUE(student_id, date),
            FOREIGN KEY (student_id) REFERENCES students(id)
        );

        CREATE TABLE IF NOT EXISTS alerts (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id   INTEGER,
            student_name TEXT    NOT NULL,
            alert_type   TEXT    NOT NULL,
            timestamp    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS attention_log (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id   INTEGER,
            student_name TEXT,
            is_attentive INTEGER DEFAULT 1,
            timestamp    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS uniform_log (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id   INTEGER,
            student_name TEXT    NOT NULL,
            is_wearing   INTEGER NOT NULL,
            timestamp    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS classroom_seats (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            class_name  TEXT    NOT NULL DEFAULT 'Class A',
            student_id  INTEGER,
            x1          INTEGER NOT NULL,
            y1          INTEGER NOT NULL,
            x2          INTEGER NOT NULL,
            y2          INTEGER NOT NULL,
            updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (student_id) REFERENCES students(id)
        );

        CREATE TABLE IF NOT EXISTS app_config (
            key         TEXT PRIMARY KEY,
            value       TEXT NOT NULL,
            updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS audit_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            actor_id    INTEGER,
            actor_role  TEXT,
            action      TEXT NOT NULL,
            entity_type TEXT,
            entity_id   TEXT,
            detail      TEXT,
            timestamp   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS bullying_incidents (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            primary_signal      TEXT    NOT NULL,
            concurrent_signals  TEXT,
            involved_names      TEXT,
            score               REAL    NOT NULL,
            duration_s          REAL,
            reviewed            INTEGER DEFAULT 0,
            review_outcome      TEXT,
            video_clip_path     TEXT
        );

        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT    NOT NULL UNIQUE,
            password_hash TEXT    NOT NULL,
            role          TEXT    NOT NULL CHECK(role IN ('teacher','parent','admin')),
            student_id    INTEGER,
            full_name     TEXT,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (student_id) REFERENCES students(id)
        );
    """)
    conn.commit()
    _migrate_alerts(conn)
    _migrate_bullying_incidents(conn)
    _migrate_students_profile(conn)
    _migrate_camera_id(conn)
    _ensure_indexes(conn)
    _seed_demo_data(conn)
    _seed_demo_users(conn)


def _migrate_bullying_incidents(conn: sqlite3.Connection):
    """Add video_clip_path column to existing bullying_incidents tables."""
    cols = [c[1] for c in conn.execute("PRAGMA table_info(bullying_incidents)").fetchall()]
    if cols and "video_clip_path" not in cols:
        conn.execute("ALTER TABLE bullying_incidents ADD COLUMN video_clip_path TEXT")
        conn.commit()
        log.info("[Mergen AI] Migrated bullying_incidents: added video_clip_path")


def _migrate_students_profile(conn: sqlite3.Connection):
    """Add per-student behavior-profile flags (IEP/ADHD/etc)."""
    cols = [c[1] for c in conn.execute("PRAGMA table_info(students)").fetchall()]
    if "attention_disabled" not in cols:
        conn.execute("ALTER TABLE students ADD COLUMN attention_disabled INTEGER DEFAULT 0")
    if "distress_disabled" not in cols:
        conn.execute("ALTER TABLE students ADD COLUMN distress_disabled INTEGER DEFAULT 0")
    if "profile_note" not in cols:
        conn.execute("ALTER TABLE students ADD COLUMN profile_note TEXT")
    conn.commit()


def _migrate_camera_id(conn: sqlite3.Connection):
    """Add camera_id (and classroom_id) to event tables for v0.3 multi-camera.

    Today the system has a single camera and writes default 1; the columns are
    added now so the schema is forward-compatible. Adding columns to existing
    rows in SQLite is a fast metadata-only operation."""
    targets = ["alerts", "attention_log", "attendance",
               "uniform_log", "bullying_incidents"]
    for tbl in targets:
        try:
            cols = [c[1] for c in conn.execute(f"PRAGMA table_info({tbl})").fetchall()]
            if not cols:
                continue
            if "camera_id" not in cols:
                conn.execute(f"ALTER TABLE {tbl} ADD COLUMN camera_id INTEGER NOT NULL DEFAULT 1")
            if "classroom_id" not in cols:
                conn.execute(f"ALTER TABLE {tbl} ADD COLUMN classroom_id INTEGER NOT NULL DEFAULT 1")
        except Exception as e:
            log.warning(f"[Mergen AI] camera_id migration on {tbl}: {e}")
    conn.commit()


def _migrate_alerts(conn: sqlite3.Connection):
    """Make alerts.student_id nullable if the old NOT NULL schema exists."""
    info = conn.execute("PRAGMA table_info(alerts)").fetchall()
    for col in info:
        if col[1] == "student_id" and col[3] == 1:  # notnull flag = 1
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS alerts_v2 (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_id   INTEGER,
                    student_name TEXT    NOT NULL,
                    alert_type   TEXT    NOT NULL,
                    timestamp    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                INSERT OR IGNORE INTO alerts_v2
                    SELECT id, student_id, student_name, alert_type, timestamp
                    FROM alerts;
                DROP TABLE alerts;
                ALTER TABLE alerts_v2 RENAME TO alerts;
            """)
            conn.commit()
            log.warning("[Mergen AI] Migrated alerts table: student_id is now nullable")
            break


def _ensure_indexes(conn: sqlite3.Connection):
    """Create indexes used by polling dashboards and date-scoped reports."""
    conn.executescript("""
        CREATE INDEX IF NOT EXISTS idx_students_role_name
            ON students(role, name);
        CREATE INDEX IF NOT EXISTS idx_attendance_date_student
            ON attendance(date, student_id);
        CREATE INDEX IF NOT EXISTS idx_alerts_date_id
            ON alerts(timestamp, id);
        CREATE INDEX IF NOT EXISTS idx_alerts_student_date
            ON alerts(student_id, timestamp);
        CREATE INDEX IF NOT EXISTS idx_attention_log_timestamp
            ON attention_log(timestamp);
        CREATE INDEX IF NOT EXISTS idx_uniform_log_student_timestamp
            ON uniform_log(student_id, timestamp);
        CREATE INDEX IF NOT EXISTS idx_bullying_timestamp
            ON bullying_incidents(timestamp);
        CREATE INDEX IF NOT EXISTS idx_bullying_review_timestamp
            ON bullying_incidents(reviewed, timestamp);
        CREATE INDEX IF NOT EXISTS idx_classroom_seats_class
            ON classroom_seats(class_name);
        CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp
            ON audit_log(timestamp);
    """)
    conn.commit()


def _seed_demo_data(conn: sqlite3.Connection):
    """Seed 3 demo students + today's attendance if DB is empty."""
    count = conn.execute("SELECT COUNT(*) FROM students").fetchone()[0]
    if count > 0:
        return

    today = date.today().isoformat()
    random.seed(42)

    demo_students = [
        ("Tenuun",      "10A", "student"),
        ("Otgonbileg",  "10A", "student"),
        ("Bataa",       "10A", "student"),
    ]

    for name, class_name, role in demo_students:
        conn.execute(
            "INSERT INTO students (name, class_name, role) VALUES (?, ?, ?)",
            (name, class_name, role),
        )

    conn.commit()
    log.info("[Mergen AI] Demo students seeded (attendance will be recorded from camera)")


# ── Student CRUD ──────────────────────────────────────────────────────────────

def save_student(name: str, class_name: str, role: str, embedding) -> int:
    """Insert a new student and return their id."""
    import numpy as np
    conn = get_db()
    blob = embedding.tobytes() if embedding is not None else None
    cur = conn.execute(
        "INSERT INTO students (name, class_name, role, face_embedding) VALUES (?, ?, ?, ?)",
        (name, class_name, role, blob),
    )
    conn.commit()
    return cur.lastrowid


def find_matching_student(embedding, threshold: float = 0.38):
    """Cosine-similarity lookup against enrolled face embeddings."""
    import numpy as np
    conn = get_db()
    rows = conn.execute(
        "SELECT id, name, class_name, face_embedding FROM students WHERE face_embedding IS NOT NULL"
    ).fetchall()

    best, best_sim = None, -1.0
    for row in rows:
        stored = np.frombuffer(row["face_embedding"], dtype=np.float32)
        if len(stored) != len(embedding):
            continue
        n_a = float(np.linalg.norm(embedding))
        n_b = float(np.linalg.norm(stored))
        if n_a > 0 and n_b > 0:
            sim = float(np.dot(embedding, stored)) / (n_a * n_b)
            if sim > best_sim:
                best_sim = sim
                best = row

    if best_sim >= threshold:
        return dict(best), best_sim
    return None, best_sim


# ── Attendance & logging ──────────────────────────────────────────────────────

def update_attendance(student_id: int, is_attentive: bool):
    conn = get_db()
    today = date.today().isoformat()
    exists = conn.execute(
        "SELECT id FROM attendance WHERE student_id=? AND date=?", (student_id, today)
    ).fetchone()

    if exists:
        if is_attentive:
            conn.execute(
                """UPDATE attendance
                   SET last_seen=datetime('now'),
                       attention_frames=attention_frames+1,
                       total_frames=total_frames+1
                   WHERE student_id=? AND date=?""",
                (student_id, today),
            )
        else:
            conn.execute(
                """UPDATE attendance
                   SET last_seen=datetime('now'), total_frames=total_frames+1
                   WHERE student_id=? AND date=?""",
                (student_id, today),
            )
    else:
        conn.execute(
            """INSERT INTO attendance (student_id, date, attention_frames, total_frames)
               VALUES (?, ?, ?, 1)""",
            (student_id, today, 1 if is_attentive else 0),
        )
    conn.commit()


def mark_seat_attendance(student_id: int):
    """Mark a student present via seat occupancy (ceiling camera mode).
    Creates/updates today's attendance row without incrementing attention frames,
    since gaze estimation is unreliable from top-down angles."""
    conn = get_db()
    today = date.today().isoformat()
    exists = conn.execute(
        "SELECT id FROM attendance WHERE student_id=? AND date=?", (student_id, today)
    ).fetchone()
    if exists:
        conn.execute(
            "UPDATE attendance SET last_seen=datetime('now') WHERE student_id=? AND date=?",
            (student_id, today),
        )
    else:
        conn.execute(
            "INSERT INTO attendance (student_id, date, attention_frames, total_frames) VALUES (?, ?, 0, 1)",
            (student_id, today),
        )
    conn.commit()


def log_attention(student_id: int, student_name: str, is_attentive: bool):
    conn = get_db()
    conn.execute(
        "INSERT INTO attention_log (student_id, student_name, is_attentive) VALUES (?, ?, ?)",
        (student_id, student_name, 1 if is_attentive else 0),
    )
    conn.commit()


def save_alert(student_id: int, student_name: str, alert_type: str) -> dict:
    """Insert an alert and return the saved row (id, name, type, timestamp)
       so callers can immediately publish it without a follow-up query."""
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO alerts (student_id, student_name, alert_type) VALUES (?, ?, ?)",
        (student_id, student_name, alert_type),
    )
    conn.commit()
    row = conn.execute(
        "SELECT id, student_id, student_name, alert_type, timestamp FROM alerts WHERE id=?",
        (cur.lastrowid,),
    ).fetchone()
    return dict(row) if row else {"id": cur.lastrowid, "student_id": student_id,
                                  "student_name": student_name, "alert_type": alert_type}


def save_unknown_alert(alert_type: str = "unknown_person") -> dict:
    """Save an alert for an unrecognised face (no student_id)."""
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO alerts (student_id, student_name, alert_type) VALUES (NULL, ?, ?)",
        ("Unknown", alert_type),
    )
    conn.commit()
    row = conn.execute(
        "SELECT id, student_id, student_name, alert_type, timestamp FROM alerts WHERE id=?",
        (cur.lastrowid,),
    ).fetchone()
    return dict(row) if row else {"id": cur.lastrowid, "student_id": None,
                                  "student_name": "Unknown", "alert_type": alert_type}


def save_bullying_incident(primary_signal: str, concurrent_signals: list,
                           involved_names: list, score: float,
                           duration_s: float) -> int:
    """Insert a bullying-incident flag for human review."""
    conn = get_db()
    cur = conn.execute(
        """INSERT INTO bullying_incidents
           (primary_signal, concurrent_signals, involved_names, score, duration_s)
           VALUES (?, ?, ?, ?, ?)""",
        (
            primary_signal,
            ",".join(concurrent_signals or []),
            ",".join(involved_names or []),
            float(score),
            float(duration_s),
        ),
    )
    conn.commit()
    return cur.lastrowid


def get_recent_bullying_incidents(since_id: int = 0, limit: int = 50):
    conn = get_db()
    rows = conn.execute(
        """SELECT id, timestamp, primary_signal, concurrent_signals,
                  involved_names, score, duration_s, reviewed, review_outcome,
                  video_clip_path
           FROM bullying_incidents
           WHERE id > ?
           ORDER BY id DESC LIMIT ?""",
        (since_id, limit),
    ).fetchall()
    return [
        {
            **dict(r),
            "concurrent_signals": [s for s in (r["concurrent_signals"] or "").split(",") if s],
            "involved_names":     [n for n in (r["involved_names"]     or "").split(",") if n],
        }
        for r in rows
    ]


def get_bullying_stats():
    conn = get_db()
    today = date.today().isoformat()
    today_ct = conn.execute(
        "SELECT COUNT(*) FROM bullying_incidents WHERE date(timestamp)=?", (today,)
    ).fetchone()[0]
    week_ct = conn.execute(
        "SELECT COUNT(*) FROM bullying_incidents WHERE timestamp >= datetime('now','-7 days')"
    ).fetchone()[0]
    pending = conn.execute(
        "SELECT COUNT(*) FROM bullying_incidents WHERE reviewed=0"
    ).fetchone()[0]
    by_signal = conn.execute(
        """SELECT primary_signal, COUNT(*) AS n
           FROM bullying_incidents
           WHERE timestamp >= datetime('now','-7 days')
           GROUP BY primary_signal ORDER BY n DESC"""
    ).fetchall()
    return {
        "today":           today_ct,
        "week":            week_ct,
        "pending_review":  pending,
        "by_signal_week":  [dict(r) for r in by_signal],
    }


def update_bullying_clip_path(incident_id: int, path: str) -> bool:
    conn = get_db()
    cur = conn.execute(
        "UPDATE bullying_incidents SET video_clip_path=? WHERE id=?",
        (path, incident_id),
    )
    conn.commit()
    return cur.rowcount > 0


def review_bullying_incident(incident_id: int, outcome: str) -> bool:
    """Mark an incident as reviewed. outcome should be one of:
       confirmed | false_positive | inconclusive."""
    conn = get_db()
    cur = conn.execute(
        "UPDATE bullying_incidents SET reviewed=1, review_outcome=? WHERE id=?",
        (outcome, incident_id),
    )
    conn.commit()
    return cur.rowcount > 0


def log_uniform(student_id: int, student_name: str, is_wearing: bool):
    conn = get_db()
    conn.execute(
        "INSERT INTO uniform_log (student_id, student_name, is_wearing) VALUES (?, ?, ?)",
        (student_id, student_name, 1 if is_wearing else 0),
    )
    conn.commit()


def get_today_uniform():
    """Latest uniform status for each student today."""
    conn = get_db()
    today = date.today().isoformat()
    rows = conn.execute(
        """SELECT s.id, s.name, s.class_name,
                  ul.is_wearing,
                  ul.timestamp as last_checked
           FROM students s
           LEFT JOIN uniform_log ul ON ul.student_id = s.id
             AND ul.id = (
               SELECT MAX(id) FROM uniform_log
               WHERE student_id = s.id AND date(timestamp) = ?
             )
           WHERE s.role = 'student'
           ORDER BY s.name""",
        (today,),
    ).fetchall()
    return [
        {
            "id":           r["id"],
            "name":         r["name"],
            "class_name":   r["class_name"],
            "is_wearing":   bool(r["is_wearing"]) if r["is_wearing"] is not None else None,
            "last_checked": r["last_checked"],
        }
        for r in rows
    ]


def get_uniform_weekly():
    """7-day average compliance per student."""
    conn = get_db()
    rows = conn.execute(
        """SELECT student_id, student_name,
                  ROUND(AVG(is_wearing) * 100, 1) AS avg_compliance
           FROM uniform_log
           WHERE timestamp >= datetime('now', '-7 days')
           GROUP BY student_id
           ORDER BY avg_compliance DESC""",
    ).fetchall()
    return [dict(r) for r in rows]


def get_uniform_stats():
    """Today's class-level uniform stats."""
    conn = get_db()
    today = date.today().isoformat()
    total = conn.execute(
        "SELECT COUNT(*) FROM students WHERE role='student'"
    ).fetchone()[0]

    # Students who have been checked today
    checked = conn.execute(
        """SELECT student_id, is_wearing
           FROM uniform_log ul
           WHERE date(timestamp) = ?
             AND id = (SELECT MAX(id) FROM uniform_log
                       WHERE student_id = ul.student_id AND date(timestamp) = ?)""",
        (today, today),
    ).fetchall()

    wearing     = sum(1 for r in checked if r["is_wearing"] == 1)
    not_wearing = sum(1 for r in checked if r["is_wearing"] == 0)
    checked_ct  = len(checked)
    rate        = round(wearing / checked_ct * 100) if checked_ct else 0

    weekly = conn.execute(
        """SELECT ROUND(AVG(is_wearing) * 100, 1)
           FROM uniform_log
           WHERE timestamp >= datetime('now', '-7 days')"""
    ).fetchone()[0]

    return {
        "total":        total,
        "wearing":      wearing,
        "not_wearing":  not_wearing,
        "checked":      checked_ct,
        "rate":         rate,
        "weekly_avg":   round(weekly or 0, 1),
    }


# ── Student management ───────────────────────────────────────────────────────

def get_student_by_id(student_id: int) -> Optional[dict]:
    conn = get_db()
    row = conn.execute("SELECT id, name, class_name, role FROM students WHERE id=?",
                       (student_id,)).fetchone()
    return dict(row) if row else None


def get_all_students():
    """Return every enrolled student with today's attendance summary."""
    conn = get_db()
    today = date.today().isoformat()
    rows = conn.execute(
        """SELECT s.id, s.name, s.class_name, s.role,
                  s.created_at,
                  CASE WHEN s.face_embedding IS NOT NULL THEN 1 ELSE 0 END AS has_face,
                  a.arrived_at,
                  a.attention_frames, a.total_frames,
                  (SELECT COUNT(*) FROM alerts al
                   WHERE al.student_id=s.id AND date(al.timestamp)=?) AS alert_count_today
           FROM students s
           LEFT JOIN attendance a ON s.id=a.student_id AND a.date=?
           ORDER BY s.name""",
        (today, today),
    ).fetchall()

    result = []
    for r in rows:
        pct = 0
        if r["total_frames"] and r["total_frames"] > 0:
            pct = round(r["attention_frames"] / r["total_frames"] * 100)
        result.append({
            "id":           r["id"],
            "name":         r["name"],
            "class_name":   r["class_name"],
            "role":         r["role"],
            "created_at":   r["created_at"],
            "has_face":     bool(r["has_face"]),
            "present_today": r["arrived_at"] is not None,
            "attention_score": pct,
            "alert_count_today": r["alert_count_today"],
        })
    return result


def delete_student(student_id: int) -> bool:
    """Delete a student and all their associated data. Returns False if not found."""
    conn = get_db()
    exists = conn.execute(
        "SELECT id FROM students WHERE id=?", (student_id,)
    ).fetchone()
    if not exists:
        return False
    conn.commit()
    conn.execute("PRAGMA foreign_keys=OFF")
    for tbl in ("attendance", "alerts", "attention_log", "uniform_log", "classroom_seats", "users"):
        try:
            conn.execute(f"DELETE FROM {tbl} WHERE student_id=?", (student_id,))
        except Exception:
            pass
    conn.execute("DELETE FROM students WHERE id=?", (student_id,))
    conn.commit()
    conn.execute("PRAGMA foreign_keys=ON")
    return True


# ── Query helpers ─────────────────────────────────────────────────────────────

def get_today_attendance():
    conn = get_db()
    today = date.today().isoformat()
    rows = conn.execute(
        """SELECT s.id, s.name, s.class_name, s.role,
                  a.arrived_at, a.last_seen,
                  a.attention_frames, a.total_frames,
                  (SELECT COUNT(*) FROM alerts al
                   WHERE al.student_id=s.id AND date(al.timestamp)=?) AS alert_count
           FROM students s
           LEFT JOIN attendance a ON s.id=a.student_id AND a.date=?
           WHERE s.role='student'
           ORDER BY s.name""",
        (today, today),
    ).fetchall()

    result = []
    for r in rows:
        pct = 0
        if r["total_frames"] and r["total_frames"] > 0:
            pct = round(r["attention_frames"] / r["total_frames"] * 100)
        result.append({
            "id":             r["id"],
            "name":           r["name"],
            "class_name":     r["class_name"],
            "arrived_at":     r["arrived_at"],
            "last_seen":      r["last_seen"],
            "attention_score": pct,
            "alert_count":    r["alert_count"],
            "present":        r["arrived_at"] is not None,
        })
    return result


def get_recent_alerts(since_id: int = 0, limit: int = 30):
    conn = get_db()
    today = date.today().isoformat()
    rows = conn.execute(
        """SELECT id, student_name, alert_type, timestamp
           FROM alerts
           WHERE id > ? AND date(timestamp) = ?
           ORDER BY id DESC LIMIT ?""",
        (since_id, today, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def get_attention_history():
    conn = get_db()
    today = date.today().isoformat()
    rows = conn.execute(
        """SELECT strftime('%H:%M', timestamp)              AS time_label,
                  ROUND(AVG(is_attentive) * 100, 1)        AS avg_attention
           FROM attention_log
           WHERE date(timestamp) = ?
           GROUP BY strftime('%H:%M', timestamp)
           ORDER BY timestamp
           LIMIT 30""",
        (today,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_admin_stats():
    conn = get_db()
    today = date.today().isoformat()
    total   = conn.execute("SELECT COUNT(*) FROM students WHERE role='student'").fetchone()[0]
    present = conn.execute(
        "SELECT COUNT(*) FROM attendance WHERE date=?", (today,)
    ).fetchone()[0]
    alerts  = conn.execute(
        "SELECT COUNT(*) FROM alerts WHERE date(timestamp)=?", (today,)
    ).fetchone()[0]
    avg_att = conn.execute(
        """SELECT ROUND(AVG(CAST(attention_frames AS FLOAT)/NULLIF(total_frames,0)*100),1)
           FROM attendance WHERE date=? AND total_frames>0""",
        (today,),
    ).fetchone()[0]
    return {
        "total_students":    total,
        "present_today":     present,
        "attendance_rate":   round(present / max(total, 1) * 100),
        "avg_attention":     avg_att or 0,
        "total_alerts":      alerts,
    }


def get_first_student():
    conn = get_db()
    row = conn.execute("SELECT id, name, class_name FROM students ORDER BY id LIMIT 1").fetchone()
    return dict(row) if row else None


# ── User auth ────────────────────────────────────────────────────────────────

_PBKDF2_ITERATIONS = 200_000


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        _PBKDF2_ITERATIONS,
    )
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${_b64(salt)}${_b64(digest)}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        if stored.startswith("pbkdf2_sha256$"):
            _, iterations, salt, expected = stored.split("$", 3)
            digest = hashlib.pbkdf2_hmac(
                "sha256",
                password.encode("utf-8"),
                _unb64(salt),
                int(iterations),
            )
            return hmac.compare_digest(_b64(digest), expected)

        # Legacy format kept for existing local demo DBs: salt:sha256(salt+password)
        salt, expected = stored.split(":", 1)
        digest = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
        return hmac.compare_digest(digest, expected)
    except Exception:
        return False


def _needs_password_rehash(stored: str) -> bool:
    return not (stored or "").startswith("pbkdf2_sha256$")


def _seed_demo_users(conn: sqlite3.Connection):
    """Always ensure demo admin/teacher/parent accounts exist (idempotent)."""
    first = conn.execute("SELECT id FROM students ORDER BY id LIMIT 1").fetchone()
    parent_sid = first["id"] if first else None
    seeded = 0
    for username, password, role, sid, full_name in [
        ("admin",    "admin123",   "admin",   None,       "Удирдлага"),
        ("teacher1", "teacher123", "teacher", None,       "Багш Батбаяр"),
        ("parent1",  "parent123",  "parent",  parent_sid, "Эцэг эх Болд"),
    ]:
        existing = conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO users (username,password_hash,role,student_id,full_name) VALUES (?,?,?,?,?)",
                (username, _hash_password(password), role, sid, full_name),
            )
            seeded += 1
    conn.commit()
    if seeded:
        log.info(f"[Mergen AI] Demo users seeded ({seeded} added)")


def create_user(username: str, password: str, role: str,
                student_id=None, full_name: str = None) -> int:
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO users (username,password_hash,role,student_id,full_name) VALUES (?,?,?,?,?)",
        (username, _hash_password(password), role, student_id, full_name),
    )
    conn.commit()
    return cur.lastrowid


def authenticate_user(username: str, password: str):
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    if not row:
        return None
    if not _verify_password(password, row["password_hash"]):
        return None
    if _needs_password_rehash(row["password_hash"]):
        conn.execute(
            "UPDATE users SET password_hash=? WHERE id=?",
            (_hash_password(password), row["id"]),
        )
        conn.commit()
    return dict(row)


def get_user_by_id(user_id: int):
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    return dict(row) if row else None


def username_exists(username: str) -> bool:
    conn = get_db()
    return conn.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone() is not None


def get_students_list():
    conn = get_db()
    rows = conn.execute(
        "SELECT id, name, class_name FROM students WHERE role='student' ORDER BY name"
    ).fetchall()
    return [dict(r) for r in rows]


def reset_today_data():
    """Clear today's records and re-seed demo attendance."""
    conn = get_db()
    today = date.today().isoformat()
    conn.execute("DELETE FROM attendance WHERE date=?", (today,))
    conn.execute("DELETE FROM alerts WHERE date(timestamp)=?", (today,))
    conn.execute("DELETE FROM attention_log WHERE date(timestamp)=?", (today,))
    conn.commit()

    # Re-seed demo students
    students = conn.execute(
        "SELECT id, name FROM students ORDER BY id LIMIT 3"
    ).fetchall()
    for s in students:
        att_pct = random.randint(65, 95)
        total   = 60
        att_f   = int(total * att_pct / 100)
        hour    = random.randint(8, 9)
        minute  = random.randint(0, 45)
        arrived = f"{today} {hour:02d}:{minute:02d}:00"
        conn.execute(
            """INSERT OR IGNORE INTO attendance
               (student_id, date, arrived_at, last_seen, attention_frames, total_frames)
               VALUES (?, ?, ?, datetime('now'), ?, ?)""",
            (s["id"], today, arrived, att_f, total),
        )
        for i in range(15):
            is_att = 1 if random.random() < att_pct / 100 else 0
            offset = -(30 - i * 2)
            conn.execute(
                """INSERT INTO attention_log (student_id, student_name, is_attentive, timestamp)
                   VALUES (?, ?, ?, datetime('now', ? || ' minutes'))""",
                (s["id"], s["name"], is_att, str(offset)),
            )
    conn.commit()


# ── Seat map ──────────────────────────────────────────────────────────────────

def get_seat_map(class_name: str = "Class A"):
    conn = get_db()
    rows = conn.execute(
        """SELECT s.id, s.class_name, s.student_id, s.x1, s.y1, s.x2, s.y2,
                  st.name AS student_name
           FROM classroom_seats s
           LEFT JOIN students st ON st.id = s.student_id
           WHERE s.class_name = ?
           ORDER BY s.id""",
        (class_name,),
    ).fetchall()
    return [dict(r) for r in rows]


def replace_seat_map(class_name: str, seats: list):
    """Atomically replace the seat map for a classroom.
       seats = [{student_id, x1, y1, x2, y2}, ...]"""
    conn = get_db()
    conn.execute("DELETE FROM classroom_seats WHERE class_name=?", (class_name,))
    for s in seats:
        conn.execute(
            """INSERT INTO classroom_seats
               (class_name, student_id, x1, y1, x2, y2)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (class_name, s.get("student_id"),
             int(s["x1"]), int(s["y1"]), int(s["x2"]), int(s["y2"])),
        )
    conn.commit()


def clear_seat_map(class_name: str = "Class A"):
    conn = get_db()
    conn.execute("DELETE FROM classroom_seats WHERE class_name=?", (class_name,))
    conn.commit()


# ── Per-student behavior profile ──────────────────────────────────────────────

def update_student_profile(student_id: int, *,
                           attention_disabled: bool = None,
                           distress_disabled: bool = None,
                           profile_note: str = None) -> bool:
    sets, vals = [], []
    if attention_disabled is not None:
        sets.append("attention_disabled=?"); vals.append(1 if attention_disabled else 0)
    if distress_disabled is not None:
        sets.append("distress_disabled=?");  vals.append(1 if distress_disabled else 0)
    if profile_note is not None:
        sets.append("profile_note=?");       vals.append(profile_note)
    if not sets:
        return False
    vals.append(student_id)
    conn = get_db()
    cur = conn.execute(
        f"UPDATE students SET {', '.join(sets)} WHERE id=?", vals,
    )
    conn.commit()
    return cur.rowcount > 0


def get_student_profile(student_id: int):
    conn = get_db()
    row = conn.execute(
        """SELECT id, name, class_name,
                  COALESCE(attention_disabled,0) AS attention_disabled,
                  COALESCE(distress_disabled,0)  AS distress_disabled,
                  profile_note
           FROM students WHERE id=?""",
        (student_id,),
    ).fetchone()
    return dict(row) if row else None


def get_attention_disabled_ids() -> set:
    conn = get_db()
    rows = conn.execute(
        "SELECT id FROM students WHERE COALESCE(attention_disabled,0)=1"
    ).fetchall()
    return {r["id"] for r in rows}


# ── App config (key/value) ────────────────────────────────────────────────────

def get_config(key: str, default: str = None):
    conn = get_db()
    row = conn.execute("SELECT value FROM app_config WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_config(key: str, value: str):
    conn = get_db()
    conn.execute(
        """INSERT INTO app_config (key, value) VALUES (?, ?)
           ON CONFLICT(key) DO UPDATE SET value=excluded.value,
                                          updated_at=CURRENT_TIMESTAMP""",
        (key, str(value)),
    )
    conn.commit()


def get_bool_config(key: str, default: bool = False) -> bool:
    raw = get_config(key, "1" if default else "0")
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def get_int_config(key: str, default: int, min_value: int = None, max_value: int = None) -> int:
    raw = get_config(key, str(default))
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = default
    if min_value is not None:
        value = max(min_value, value)
    if max_value is not None:
        value = min(max_value, value)
    return value


def log_audit(action: str, actor: dict = None, entity_type: str = None,
              entity_id: str = None, detail: str = None):
    conn = get_db()
    actor_id = actor.get("id") if actor else None
    actor_role = actor.get("role") if actor else None
    conn.execute(
        """INSERT INTO audit_log
              (actor_id, actor_role, action, entity_type, entity_id, detail)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (actor_id, actor_role, action, entity_type, entity_id, detail),
    )
    conn.commit()


def get_audit_log(limit: int = 80):
    conn = get_db()
    limit = max(1, min(int(limit), 200))
    rows = conn.execute(
        """SELECT id, actor_id, actor_role, action, entity_type, entity_id, detail, timestamp
           FROM audit_log
           ORDER BY id DESC
           LIMIT ?""",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


# ── Data retention / purge ────────────────────────────────────────────────────

def purge_old_data(retention_days: int) -> dict:
    """Delete rows older than retention_days from all time-series tables.
       Returns counts deleted per table."""
    conn = get_db()
    cutoff = f"datetime('now','-{int(retention_days)} days')"
    counts = {}
    for table, ts_col in [
        ("attention_log",      "timestamp"),
        ("alerts",             "timestamp"),
        ("uniform_log",        "timestamp"),
        ("bullying_incidents", "timestamp"),
        ("attendance",         "arrived_at"),
    ]:
        cur = conn.execute(f"DELETE FROM {table} WHERE {ts_col} < {cutoff}")
        counts[table] = cur.rowcount
    conn.commit()
    return counts


# ── Threshold-tuning suggestion (from review feedback) ────────────────────────

def get_review_stats_by_signal():
    """For each primary_signal, count confirmed vs false_positive reviews and
       compute a precision-like score and a suggested threshold delta."""
    conn = get_db()
    rows = conn.execute(
        """SELECT primary_signal,
                  SUM(CASE WHEN review_outcome='confirmed'      THEN 1 ELSE 0 END) AS confirmed,
                  SUM(CASE WHEN review_outcome='false_positive' THEN 1 ELSE 0 END) AS false_pos,
                  SUM(CASE WHEN review_outcome='inconclusive'   THEN 1 ELSE 0 END) AS inconc,
                  AVG(CASE WHEN review_outcome='confirmed'      THEN score END)    AS avg_score_conf,
                  AVG(CASE WHEN review_outcome='false_positive' THEN score END)    AS avg_score_fp,
                  COUNT(*)                                                          AS reviewed
           FROM bullying_incidents
           WHERE reviewed=1
           GROUP BY primary_signal"""
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        total = max((d["confirmed"] or 0) + (d["false_pos"] or 0), 1)
        d["precision"] = round((d["confirmed"] or 0) / total, 3)
        # Heuristic suggestion: midpoint between false-positive and confirmed average score.
        if d["avg_score_fp"] is not None and d["avg_score_conf"] is not None:
            d["suggested_threshold"] = round((d["avg_score_fp"] + d["avg_score_conf"]) / 2, 2)
        else:
            d["suggested_threshold"] = None
        out.append(d)
    return out
