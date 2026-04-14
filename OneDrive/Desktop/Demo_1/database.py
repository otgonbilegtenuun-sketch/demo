"""
database.py — SQLite setup, queries, and demo seed data.
All tables use WAL mode for safe concurrent access from the camera thread.
"""

import sqlite3
import threading
import random
from datetime import date, datetime

DB_PATH = "classroom.db"
_thread_local = threading.local()


def get_db() -> sqlite3.Connection:
    """Return a per-thread SQLite connection (WAL mode, row factory)."""
    if not hasattr(_thread_local, "conn"):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
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
    """)
    conn.commit()
    _migrate_alerts(conn)
    _seed_demo_data(conn)


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
            print("[EduGuard] Migrated alerts table: student_id is now nullable")
            break


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
        cur = conn.execute(
            "INSERT INTO students (name, class_name, role) VALUES (?, ?, ?)",
            (name, class_name, role),
        )
        sid = cur.lastrowid

        # Seed realistic attendance data for today
        attention_pct = random.randint(68, 94)
        total = 60
        att_frames = int(total * attention_pct / 100)
        hour = random.randint(8, 9)
        minute = random.randint(0, 45)
        arrived = f"{today} {hour:02d}:{minute:02d}:00"

        conn.execute(
            """INSERT OR IGNORE INTO attendance
               (student_id, date, arrived_at, last_seen, attention_frames, total_frames)
               VALUES (?, ?, ?, datetime('now'), ?, ?)""",
            (sid, today, arrived, att_frames, total),
        )

        # Seed attention log (last 30 minutes, every 2 min)
        for i in range(15):
            is_att = 1 if random.random() < attention_pct / 100 else 0
            offset = -(30 - i * 2)
            conn.execute(
                """INSERT INTO attention_log (student_id, student_name, is_attentive, timestamp)
                   VALUES (?, ?, ?, datetime('now', ? || ' minutes'))""",
                (sid, name, is_att, str(offset)),
            )

    # Seed two demo alerts
    conn.execute(
        """INSERT INTO alerts (student_id, student_name, alert_type, timestamp)
           VALUES (1, 'Tenuun', 'suspicious_glance', datetime('now', '-12 minutes'))"""
    )
    conn.execute(
        """INSERT INTO alerts (student_id, student_name, alert_type, timestamp)
           VALUES (2, 'Otgonbileg', 'phone_detected', datetime('now', '-6 minutes'))"""
    )
    conn.commit()


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


def find_matching_student(embedding, threshold: float = 0.65):
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


def log_attention(student_id: int, student_name: str, is_attentive: bool):
    conn = get_db()
    conn.execute(
        "INSERT INTO attention_log (student_id, student_name, is_attentive) VALUES (?, ?, ?)",
        (student_id, student_name, 1 if is_attentive else 0),
    )
    conn.commit()


def save_alert(student_id: int, student_name: str, alert_type: str):
    conn = get_db()
    conn.execute(
        "INSERT INTO alerts (student_id, student_name, alert_type) VALUES (?, ?, ?)",
        (student_id, student_name, alert_type),
    )
    conn.commit()


def save_unknown_alert(alert_type: str = "unknown_person"):
    """Save an alert for an unrecognised face (no student_id)."""
    conn = get_db()
    conn.execute(
        "INSERT INTO alerts (student_id, student_name, alert_type) VALUES (NULL, ?, ?)",
        ("Unknown", alert_type),
    )
    conn.commit()


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
    # Cascade delete related records
    conn.execute("DELETE FROM attendance    WHERE student_id=?", (student_id,))
    conn.execute("DELETE FROM alerts        WHERE student_id=?", (student_id,))
    conn.execute("DELETE FROM attention_log WHERE student_id=?", (student_id,))
    conn.execute("DELETE FROM students      WHERE id=?",         (student_id,))
    conn.commit()
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
