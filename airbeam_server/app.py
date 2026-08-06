"""
AirBeam Research Server
-----------------------
Run with:  python app.py
Requires:  pip install flask flask-cors

All data is stored in airbeam.db (SQLite) in the same folder.
"""

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import sqlite3, json, os

app = Flask(__name__, static_folder="static", template_folder="templates")
CORS(app)

DB = os.path.join(os.path.dirname(__file__), "airbeam.db")
ADMIN_PIN = os.environ.get("ADMIN_PIN", "airbeam2026")

def _is_admin():
    return request.headers.get("X-Admin-Pin", "") == ADMIN_PIN

# ── Database setup ────────────────────────────────────────────────────────────
def get_db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    with get_db() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            sheet     TEXT UNIQUE,
            category  TEXT,
            name      TEXT,
            date      TEXT,
            time      TEXT,
            trial     INTEGER DEFAULT 0,
            location  TEXT DEFAULT '',
            iv1       TEXT DEFAULT '',
            iv2       TEXT DEFAULT '',
            iv3       TEXT DEFAULT '',
            iv4       TEXT DEFAULT '',
            iv_extra  TEXT DEFAULT '{}',
            pm1       REAL,
            pm25      REAL,
            pm10      REAL,
            temp      REAL,
            humidity  REAL,
            notes     TEXT DEFAULT '',
            max_pm25  REAL,
            time_series TEXT DEFAULT '[]',
            note_markers TEXT DEFAULT '[]',
            note_photos  TEXT DEFAULT '[]',
            qa_thread    TEXT DEFAULT '[]'
        );

        CREATE TABLE IF NOT EXISTS scenarios (
            category TEXT PRIMARY KEY,
            scenario TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS custom_categories (
            name TEXT PRIMARY KEY,
            hex  TEXT,
            text_color TEXT,
            icon TEXT,
            iv_labels TEXT DEFAULT '[]'
        );

        CREATE TABLE IF NOT EXISTS custom_iv_tags (
            category TEXT NOT NULL,
            label    TEXT NOT NULL,
            tags     TEXT DEFAULT '[]',
            PRIMARY KEY (category, label)
        );

        CREATE TABLE IF NOT EXISTS users (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            display_name TEXT NOT NULL,
            pin          TEXT UNIQUE NOT NULL,
            role         TEXT NOT NULL DEFAULT 'viewer'
        );
        """)
    print("Database ready:", DB)

init_db()

# Migrate existing DB
def migrate_db():
    with get_db() as con:
        try:
            con.execute("ALTER TABLE sessions ADD COLUMN gps_path TEXT DEFAULT '[]'")
        except:
            pass
        try:
            con.execute("ALTER TABLE sessions ADD COLUMN qa_thread TEXT DEFAULT '[]'")
        except:
            pass
        try:
            con.execute("ALTER TABLE sessions ADD COLUMN uploaded_by TEXT DEFAULT ''")
        except:
            pass
        try:
            con.execute("ALTER TABLE custom_categories ADD COLUMN iv_labels TEXT DEFAULT '[]'")
        except:
            pass
        try:
            con.execute("ALTER TABLE sessions ADD COLUMN iv_extra TEXT DEFAULT '{}'")
        except:
            pass
        try:
            con.execute("ALTER TABLE custom_categories ADD COLUMN display_name TEXT DEFAULT ''")
        except:
            pass
        try:
            con.execute("ALTER TABLE custom_categories ADD COLUMN hidden INTEGER DEFAULT 0")
        except:
            pass
        # Seed default users if table is empty
        count = con.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if count == 0:
            con.executemany(
                "INSERT OR IGNORE INTO users (display_name, pin, role) VALUES (?,?,?)",
                [("Christine", "xS0p1z6SSJ", "teamlead"),
                 ("Viewer", "airbeam-view", "viewer")]
            )
migrate_db()

# ── Static files ──────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory("templates", "index.html")

# ── Sessions API ──────────────────────────────────────────────────────────────
@app.route("/api/sessions", methods=["GET"])
def get_sessions():
    with get_db() as con:
        rows = con.execute("SELECT * FROM sessions ORDER BY category, trial").fetchall()
    sessions = []
    for r in rows:
        s = dict(r)
        s["timeSeries"]   = json.loads(s.pop("time_series",  "[]") or "[]")
        s["noteMarkers"]  = json.loads(s.pop("note_markers", "[]") or "[]")
        s["notePhotos"]   = json.loads(s.pop("note_photos",  "[]") or "[]")
        s["gpsPath"]      = json.loads(s.pop("gps_path",     "[]") or "[]")
        s["qaThread"]     = json.loads(s.pop("qa_thread",    "[]") or "[]")
        s["maxPm25"]      = s.pop("max_pm25", None)
        s["uploadedBy"]   = s.pop("uploaded_by", "") or ""
        s["ivExtra"]      = json.loads(s.pop("iv_extra", "{}") or "{}")
        sessions.append(s)
    return jsonify(sessions)

@app.route("/api/sessions", methods=["POST"])
def upsert_sessions():
    """Bulk upsert sessions (called when uploading merged_sessions.xlsx)"""
    data = request.get_json()
    sessions = data if isinstance(data, list) else [data]
    with get_db() as con:
        for s in sessions:
            con.execute("""
                INSERT INTO sessions
                  (sheet,category,name,date,time,trial,location,iv1,iv2,iv3,iv4,iv_extra,
                   pm1,pm25,pm10,temp,humidity,notes,max_pm25,time_series,note_markers,note_photos,gps_path,qa_thread,uploaded_by)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(sheet) DO UPDATE SET
                  time_series=excluded.time_series,
                  note_markers=excluded.note_markers,
                  gps_path=excluded.gps_path,
                  qa_thread=excluded.qa_thread,
                  category=excluded.category,
                  name=excluded.name,
                  date=excluded.date,
                  time=excluded.time,
                  trial=excluded.trial,
                  pm1=excluded.pm1,
                  pm25=excluded.pm25,
                  pm10=excluded.pm10,
                  temp=excluded.temp,
                  humidity=excluded.humidity,
                  max_pm25=excluded.max_pm25
            """, (
                s.get("sheet"), s.get("category"), s.get("name"),
                s.get("date"), s.get("time"), s.get("trial",""),
                s.get("location",""), s.get("iv1",""), s.get("iv2",""),
                s.get("iv3",""), s.get("iv4",""), json.dumps(s.get("ivExtra",{})),
                s.get("pm1"), s.get("pm25"), s.get("pm10"),
                s.get("temp"), s.get("humidity"), s.get("notes",""),
                s.get("maxPm25"),
                json.dumps(s.get("timeSeries",[])),
                json.dumps(s.get("noteMarkers",[])),
                json.dumps(s.get("notePhotos",[])),
                json.dumps(s.get("gpsPath",[])),
                json.dumps(s.get("qaThread",[])),
                s.get("uploadedBy","")
            ))
        # Recalculate trial numbers after bulk insert
        _recalc_trials(con)
    return jsonify({"ok": True})

@app.route("/api/sessions/<int:sid>", methods=["PUT"])
def update_session(sid):
    """Update a single session's editable fields — only updates fields that are present in the request"""
    s = request.get_json()
    with get_db() as con:
        # Fetch existing row first
        row = con.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
        if not row:
            return jsonify({"ok": False, "error": "Not found"}), 404
        existing = dict(row)
        # Q&A updates are allowed for any authenticated user; all other edits require ownership
        qa_only = set(s.keys()) <= {"qaThread"}
        if qa_only:
            if not _is_authenticated(con):
                return jsonify({"ok": False, "error": "Forbidden"}), 403
        else:
            if not _owns_session(con, existing):
                return jsonify({"ok": False, "error": "Forbidden"}), 403
        # Only update fields that were actually sent
        new_category = s.get("category", existing.get("category",""))
        con.execute("""
            UPDATE sessions SET
              category=?, location=?, iv1=?, iv2=?, iv3=?, iv4=?, iv_extra=?,
              notes=?, trial=?, note_photos=?, note_markers=?, qa_thread=?,
              pm1=?, pm25=?, pm10=?, temp=?, humidity=?
            WHERE id=?
        """, (
            new_category,
            s.get("location", existing.get("location","")),
            s.get("iv1",     existing.get("iv1","")),
            s.get("iv2",     existing.get("iv2","")),
            s.get("iv3",     existing.get("iv3","")),
            s.get("iv4",     existing.get("iv4","")),
            json.dumps(s.get("ivExtra", json.loads(existing.get("iv_extra","{}") or "{}"))),
            s.get("notes",   existing.get("notes","")),
            s.get("trial",   existing.get("trial","")),
            json.dumps(s.get("notePhotos",   json.loads(existing.get("note_photos",  "[]") or "[]"))),
            json.dumps(s.get("noteMarkers",  json.loads(existing.get("note_markers", "[]") or "[]"))),
            json.dumps(s.get("qaThread",     json.loads(existing.get("qa_thread",    "[]") or "[]"))),
            s.get("pm1",     existing.get("pm1")),
            s.get("pm25",    existing.get("pm25")),
            s.get("pm10",    existing.get("pm10")),
            s.get("temp",    existing.get("temp")),
            s.get("humidity",existing.get("humidity")),
            sid
        ))
        if new_category != existing.get("category",""):
            _recalc_trials(con)
    return jsonify({"ok": True})

@app.route("/api/sessions/<int:sid>", methods=["DELETE"])
def delete_session(sid):
    with get_db() as con:
        row = con.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
        if not row:
            return jsonify({"ok": False, "error": "Not found"}), 404
        if not _owns_session(con, dict(row)):
            return jsonify({"ok": False, "error": "Forbidden"}), 403
        con.execute("DELETE FROM sessions WHERE id=?", (sid,))
    return jsonify({"ok": True})

@app.route("/api/sessions/new", methods=["POST"])
def add_session():
    """Add a manually created session"""
    s = request.get_json()
    with get_db() as con:
        cur = con.execute("""
            INSERT INTO sessions
              (sheet,category,name,date,time,trial,location,iv1,iv2,iv3,iv4,iv_extra,
               pm1,pm25,pm10,temp,humidity,notes,max_pm25,time_series,note_markers,note_photos,uploaded_by)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            s.get("sheet", "manual_"+str(os.urandom(4).hex())),
            s.get("category"), s.get("name",""),
            s.get("date"), s.get("time"), s.get("trial",""),
            s.get("location",""), s.get("iv1",""), s.get("iv2",""),
            s.get("iv3",""), s.get("iv4",""), json.dumps(s.get("ivExtra",{})),
            s.get("pm1"), s.get("pm25"), s.get("pm10"),
            s.get("temp"), s.get("humidity"), s.get("notes",""),
            s.get("maxPm25"),
            json.dumps([]), json.dumps([]), json.dumps([]),
            s.get("uploadedBy","")
        ))
        new_id = cur.lastrowid
        _recalc_trials(con)
    return jsonify({"ok": True, "id": new_id})

# ── Scenarios API ─────────────────────────────────────────────────────────────
@app.route("/api/scenarios", methods=["GET"])
def get_scenarios():
    with get_db() as con:
        rows = con.execute("SELECT category, scenario FROM scenarios").fetchall()
    return jsonify({r["category"]: r["scenario"] for r in rows})

@app.route("/api/scenarios/<category>", methods=["PUT"])
def set_scenario(category):
    text = request.get_json().get("scenario","")
    with get_db() as con:
        con.execute("""
            INSERT INTO scenarios (category, scenario) VALUES (?,?)
            ON CONFLICT(category) DO UPDATE SET scenario=excluded.scenario
        """, (category, text))
    return jsonify({"ok": True})

# ── Custom categories API ─────────────────────────────────────────────────────
@app.route("/api/categories/<name>/iv-labels", methods=["PUT"])
def update_iv_labels(name):
    data = request.get_json()
    iv_labels = data.get("ivLabels", [])
    with get_db() as con:
        # Upsert — works for both custom and built-in categories
        con.execute("""
            INSERT INTO custom_categories (name, hex, text_color, icon, iv_labels)
            VALUES (?, '', '', '', ?)
            ON CONFLICT(name) DO UPDATE SET iv_labels=excluded.iv_labels
        """, (name, json.dumps(iv_labels)))
    return jsonify({"ok": True})

@app.route("/api/categories", methods=["GET"])
def get_categories():
    with get_db() as con:
        rows = con.execute("SELECT * FROM custom_categories").fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["ivLabels"] = json.loads(d.pop("iv_labels", "[]") or "[]")
        d["displayName"] = d.pop("display_name", "") or ""
        d["hidden"] = bool(d.get("hidden", 0))
        result.append(d)
    return jsonify(result)

@app.route("/api/iv-tags", methods=["GET"])
def get_iv_tags():
    with get_db() as con:
        rows = con.execute("SELECT category, label, tags FROM custom_iv_tags").fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["tags"] = json.loads(d.get("tags", "[]") or "[]")
        result.append(d)
    return jsonify(result)

@app.route("/api/iv-tags", methods=["PUT"])
def update_iv_tags():
    # category/label are passed in the body (not the URL path) so that
    # labels containing special characters like "/" or "#" -- e.g.
    # "Type / # of Pets" -- can't ever break Flask's route matching.
    # (A "/api/categories/<category>/tags/<label>" path previously used
    # here would silently 404 on any label containing a slash, even when
    # correctly percent-encoded by the browser, because Flask/Werkzeug's
    # default routing treats a decoded "/" as a path separator.)
    data = request.get_json()
    category = data.get("category", "")
    label = data.get("label", "")
    tags = data.get("tags", [])
    if not category or not label:
        return jsonify({"ok": False, "error": "category and label are required"}), 400
    with get_db() as con:
        con.execute("""
            INSERT INTO custom_iv_tags (category, label, tags)
            VALUES (?, ?, ?)
            ON CONFLICT(category, label) DO UPDATE SET tags=excluded.tags
        """, (category, label, json.dumps(tags)))
    return jsonify({"ok": True})

@app.route("/api/categories", methods=["POST"])
def add_category():
    c = request.get_json()
    with get_db() as con:
        con.execute("""
            INSERT OR IGNORE INTO custom_categories (name,hex,text_color,icon,iv_labels)
            VALUES (?,?,?,?,?)
        """, (c["name"], c["hex"], c["text"], c["icon"],
              json.dumps(c.get("ivLabels", []))))
    return jsonify({"ok": True})

@app.route("/api/categories/<name>/rename", methods=["PATCH"])
def rename_category(name):
    if not _is_admin():
        return jsonify({"error": "Unauthorized"}), 403
    data = request.get_json()
    new_display = (data.get("displayName") or "").strip()
    if not new_display:
        return jsonify({"ok": False, "error": "Name required"}), 400
    with get_db() as con:
        con.execute("""
            INSERT INTO custom_categories (name, hex, text_color, icon, iv_labels, display_name)
            VALUES (?, '', '', '', '[]', ?)
            ON CONFLICT(name) DO UPDATE SET display_name=excluded.display_name
        """, (name, new_display))
    return jsonify({"ok": True})

@app.route("/api/categories/<name>", methods=["DELETE"])
def delete_category(name):
    if not _is_admin():
        return jsonify({"error": "Unauthorized"}), 403
    with get_db() as con:
        row = con.execute("SELECT * FROM custom_categories WHERE name=?", (name,)).fetchone()
        if row:
            # If it came from custom_categories, check if it's truly custom
            # (built-ins may have been written there for iv_labels etc.)
            # We soft-delete by setting hidden=1 so data is preserved
            con.execute("""
                INSERT INTO custom_categories (name, hex, text_color, icon, iv_labels, hidden)
                VALUES (?, '', '', '', '[]', 1)
                ON CONFLICT(name) DO UPDATE SET hidden=1
            """, (name,))
        else:
            # No row yet for a built-in: create a hidden tombstone
            con.execute("""
                INSERT OR IGNORE INTO custom_categories (name, hex, text_color, icon, iv_labels, hidden)
                VALUES (?, '', '', '', '[]', 1)
            """, (name,))
    return jsonify({"ok": True})

# ── Helpers ───────────────────────────────────────────────────────────────────
def _owns_session(con, session_row):
    """Return True if the requesting user is admin or uploaded this session."""
    pin = request.headers.get("X-User-Pin", "")
    if pin == ADMIN_PIN:
        return True
    if not pin:
        return False
    user = con.execute("SELECT display_name FROM users WHERE pin=?", (pin,)).fetchone()
    if not user:
        return False
    return user["display_name"] == (session_row.get("uploaded_by") or "")

def _is_authenticated(con):
    """Return True if the requesting user has any valid pin (admin or registered user)."""
    pin = request.headers.get("X-User-Pin", "")
    if not pin:
        return False
    if pin == ADMIN_PIN:
        return True
    return con.execute("SELECT 1 FROM users WHERE pin=?", (pin,)).fetchone() is not None

def _recalc_trials(con):
    """Re-number trials within each category by date+time ascending"""
    rows = con.execute("SELECT id, category, date, time FROM sessions").fetchall()
    by_cat = {}
    for r in rows:
        by_cat.setdefault(r["category"], []).append(dict(r))
    for cat, ss in by_cat.items():
        ss.sort(key=lambda s: (s["date"] or "", s["time"] or ""))
        for i, s in enumerate(ss):
            con.execute("UPDATE sessions SET trial=? WHERE id=?", (i+1, s["id"]))

# ── Auth API ──────────────────────────────────────────────────────────────────
@app.route("/api/auth", methods=["POST"])
def auth():
    pin = request.get_json().get("pin", "")
    with get_db() as con:
        row = con.execute("SELECT * FROM users WHERE pin=?", (pin,)).fetchone()
    if not row:
        return jsonify({"ok": False}), 401
    return jsonify({"ok": True, "role": row["role"], "displayName": row["display_name"]})

# ── Users API ─────────────────────────────────────────────────────────────────
@app.route("/api/users", methods=["GET"])
def get_users():
    if not _is_admin():
        return jsonify({"error": "Unauthorized"}), 403
    with get_db() as con:
        rows = con.execute("SELECT id, display_name, pin, role FROM users ORDER BY id").fetchall()
    return jsonify([dict(r) for r in rows])

@app.route("/api/users", methods=["POST"])
def create_user():
    if not _is_admin():
        return jsonify({"error": "Unauthorized"}), 403
    u = request.get_json()
    display_name = (u.get("displayName") or "").strip()
    pin = (u.get("pin") or "").strip()
    role = u.get("role", "viewer")
    if not display_name or not pin:
        return jsonify({"ok": False, "error": "Name and PIN are required"}), 400
    if role not in ("viewer", "teamlead", "researcher"):
        return jsonify({"ok": False, "error": "Invalid role"}), 400
    if pin == ADMIN_PIN:
        return jsonify({"ok": False, "error": "PIN already in use"}), 409
    try:
        with get_db() as con:
            cur = con.execute(
                "INSERT INTO users (display_name, pin, role) VALUES (?,?,?)",
                (display_name, pin, role)
            )
        return jsonify({"ok": True, "id": cur.lastrowid})
    except sqlite3.IntegrityError:
        return jsonify({"ok": False, "error": "PIN already in use"}), 409

@app.route("/api/users/<int:uid>", methods=["PUT"])
def update_user(uid):
    if not _is_admin():
        return jsonify({"error": "Unauthorized"}), 403
    u = request.get_json()
    with get_db() as con:
        row = con.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        if not row:
            return jsonify({"ok": False, "error": "Not found"}), 404
        existing = dict(row)
        new_pin = (u.get("pin") or existing["pin"]).strip()
        if new_pin == ADMIN_PIN:
            return jsonify({"ok": False, "error": "PIN already in use"}), 409
        new_role = u.get("role", existing["role"])
        if new_role not in ("viewer", "teamlead", "researcher"):
            return jsonify({"ok": False, "error": "Invalid role"}), 400
        try:
            con.execute(
                "UPDATE users SET display_name=?, pin=?, role=? WHERE id=?",
                (
                    (u.get("displayName") or existing["display_name"]).strip(),
                    new_pin,
                    new_role,
                    uid
                )
            )
        except sqlite3.IntegrityError:
            return jsonify({"ok": False, "error": "PIN already in use"}), 409
    return jsonify({"ok": True})

@app.route("/api/users/<int:uid>", methods=["DELETE"])
def delete_user(uid):
    if not _is_admin():
        return jsonify({"error": "Unauthorized"}), 403
    with get_db() as con:
        con.execute("DELETE FROM users WHERE id=?", (uid,))
    return jsonify({"ok": True})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
