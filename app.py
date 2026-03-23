from flask import Flask, request, jsonify, send_from_directory, session
import sqlite3
from datetime import datetime, timedelta
import pytz
import time

app = Flask(__name__)
app.secret_key = "supersecretkey"  # palitan mo ito ng mas secure na string

PH_TZ = pytz.timezone("Asia/Manila")

# --- Simple in-memory cache for scoreboard ---
scoreboard_cache = {"data": None, "timestamp": 0}

# --- Initialize DB with candidates ---
def init_db():
    conn = sqlite3.connect("votes.db")
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS candidates (
            id TEXT PRIMARY KEY,
            name TEXT,
            org TEXT,
            program TEXT,
            gender TEXT,
            image TEXT,
            votes INTEGER DEFAULT 0
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS votes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id TEXT,
            candidate_id TEXT,
            gender TEXT,
            timestamp TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fb_reactions (
            candidate_id TEXT PRIMARY KEY,
            reactions INTEGER DEFAULT 0
        )
    """)

    candidates = [
        ("cand001","Benj Anthony Gabo","Ugnayang Kayumanggi","BSE Filipino","male","mr1.jpg"),
        ("cand002","Lance Christopher Calixto","HM Society","BSHM","male","mr2.jpg"),
        ("cand003","Yuan Sales","Daskalos Coalition","BEED","male","mr3.jpg"),
        ("cand004","Neo Salangsang","Daskalos Coalition","BEED","male","mr4.jpg"),
        ("cand005","Victor Angello Dauag","The Elite Guild","BSE English","male","mr5.jpg"),
        ("cand006","John Edward Sabado","Ugnayang Kayumanggi","BSE Filipino","male","mr6.jpg"),
        ("cand007","Diego Salvador Sandico","HM Society","BSHM","male","mr7.jpg"),
        ("cand008","Alex Ventilacion","The Elite Guild","BSE English","male","mr8.jpg"),
        ("cand009","Denise Banaag","Ugnayang Kayumanggi","BSE Filipino","female","ms1.jpg"),
        ("cand010","Kiara Andrie Simon","HM Society","BSHM","female","ms2.jpg"),
        ("cand011","Ryzamae Ballesteros","Daskalos Coalition","BEED","female","ms3.jpg"),
        ("cand012","Jonalyn Tepace","Daskalos Coalition","BEED","female","ms4.jpg"),
        ("cand013","Nadine Marinay","The Elite Guild","BSE English","female","ms5.jpg"),
        ("cand014","Ashley Kate Lobarbio","Ugnayang Kayumanggi","BSE Filipino","female","ms6.jpg"),
        ("cand015","Jonna Marie Azarcon","HM Society","BSHM","female","ms7.jpg"),
        ("cand016","Jhasmine Joy Lucambo","The Elite Guild","BSE English","female","ms8.jpg"),
    ]
    for cand in candidates:
        cursor.execute("""
        INSERT OR IGNORE INTO candidates (id, name, org, program, gender, image, votes)
        VALUES (?, ?, ?, ?, ?, ?, 0)
    """, cand)

    conn.commit()
    conn.close()

init_db()

# --- Helper function to get results (admin full view) ---
def get_results():
    conn = sqlite3.connect("votes.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.id, c.name, c.org, c.program, c.gender, c.image,
               c.votes AS system_votes,
               IFNULL(f.reactions, 0) AS fb_reactions,
               ROUND(((c.votes * 0.5) + (IFNULL(f.reactions, 0) * 0.5)), 2) AS darling_score
        FROM candidates c
        LEFT JOIN fb_reactions f ON c.id = f.candidate_id
        ORDER BY darling_score DESC
    """)
    rows = cursor.fetchall()
    conn.close()

    results = []
    for row in rows:
        results.append({
            "id": row[0],
            "name": row[1],
            "org": row[2],
            "program": row[3],
            "gender": row[4],
            "image": row[5],
            "system_votes": row[6],
            "fb_reactions": row[7],
            "darling_score": row[8]
        })
    return results

# --- Voting endpoint ---
@app.route("/vote", methods=["POST"])
def vote():
    data = request.get_json()
    ticket_id = data.get("ticket_id")
    candidate_id = data.get("candidate_id")
    gender = data.get("gender")

    now = datetime.now(PH_TZ)
    start = PH_TZ.localize(datetime(2026, 3, 23, 11, 0, 0))
    end = PH_TZ.localize(datetime(2026, 3, 30, 12, 0, 0))

    if now < start or now > end:
        return jsonify({"message": "Voting is closed. Valid period is March 23–30, Philippine Time."}), 400

    conn = sqlite3.connect("votes.db")
    cursor = conn.cursor()

    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1, seconds=-1)

    cursor.execute("""
        SELECT COUNT(*) FROM votes
        WHERE ticket_id=? AND gender=? AND timestamp BETWEEN ? AND ?
    """, (ticket_id, gender, today_start.isoformat(), today_end.isoformat()))
    already_voted = cursor.fetchone()[0]

    if already_voted > 0:
        conn.close()
        return jsonify({"message": "You have already voted today for this category."}), 400

    cursor.execute("""
        INSERT INTO votes (ticket_id, candidate_id, gender, timestamp)
        VALUES (?, ?, ?, ?)
    """, (ticket_id, candidate_id, gender, now.isoformat()))

    cursor.execute("UPDATE candidates SET votes = votes + 1 WHERE id=?", (candidate_id,))
    conn.commit()
    conn.close()

    # Invalidate scoreboard cache after new vote
    scoreboard_cache["data"] = None
    scoreboard_cache["timestamp"] = 0

    return jsonify({"message": "Vote recorded successfully."}), 200

# --- Results endpoint (admin full view) ---
@app.route("/results", methods=["GET"])
def results():
    data = get_results()
    return jsonify(data)

# --- Public scoreboard with caching ---
@app.route("/public_scoreboard", methods=["GET"])
def public_scoreboard():
    now = time.time()
    if scoreboard_cache["data"] and (now - scoreboard_cache["timestamp"] < 10):
        return jsonify(scoreboard_cache["data"]), 200

    conn = sqlite3.connect("votes.db")
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM votes WHERE gender='male'")
    male_votes = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM votes WHERE gender='female'")
    female_votes = cursor.fetchone()[0]

    if male_votes < 20 or female_votes < 20:
        conn.close()
        data = {"message": "Scoreboard will be available once each category reaches 20 votes."}
        scoreboard_cache["data"] = data
        scoreboard_cache["timestamp"] = now
        return jsonify(data), 200

    cursor.execute("SELECT id FROM candidates WHERE gender='male'")
    male_ids = [row[0] for row in cursor.fetchall()]
    cursor.execute("SELECT id FROM candidates WHERE gender='female'")
    female_ids = [row[0] for row in cursor.fetchall()]

    def compute_percent(ids, gender):
        results = []
        total = conn.execute("SELECT COUNT(*) FROM votes WHERE gender=?", (gender,)).fetchone()[0]
        for idx, cid in enumerate(ids):
            count = conn.execute("SELECT COUNT(*) FROM votes WHERE candidate_id=? AND gender=?", (cid, gender)).fetchone()[0]
            percent = round((count / total) * 100, 2) if total > 0 else 0
            letter = chr(65 + idx)  # A, B, C...
            results.append({"letter": letter, "percent": percent})
        return results

    male_results = compute_percent(male_ids, "male")
    female_results = compute_percent(female_ids, "female")

    conn.close()

    data = {"male": male_results, "female": female_results}
    scoreboard_cache["data"] = data
    scoreboard_cache["timestamp"] = now

    return jsonify(data), 200

# --- Update FB reactions endpoint (protected) ---
@app.route("/update_fb", methods=["POST"])
def update_fb():
    if not session.get("admin_logged_in"):
        return jsonify({"message": "Unauthorized"}), 403

    data = request.get_json()
    candidate_id = str(data.get("candidate_id"))
    reactions = int(data.get("reactions"))

    conn = sqlite3.connect("votes.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO fb_reactions (candidate_id, reactions)
        VALUES (?, ?)
        ON CONFLICT(candidate_id) DO UPDATE SET reactions=excluded.reactions
    """, (candidate_id, reactions))
    conn.commit()
    conn.close()

    # Invalidate scoreboard cache after FB update
    scoreboard_cache["data"] = None
    scoreboard_cache["timestamp"] = 0

    return jsonify({"message": f"FB reactions updated for candidate {candidate_id}."}), 200

# --- Admin login/logout ---
@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    password = data.get("password")
    if password == "admin123":  # palitan mo ito ng mas secure na password
        session["admin_logged_in"] = True
        return jsonify({"message": "Login successful"}), 200
    else:
        return jsonify({"message": "Invalid password"}), 403

@app.route("/logout", methods=["POST"])
def logout():
    session.pop("admin_logged_in", None)
    return jsonify({"message": "Logged out"}), 200

# --- Serve frontend folder ---
@app.route("/<path:filename>")
def frontend_files(filename):
    return send_from_directory("frontend", filename)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)