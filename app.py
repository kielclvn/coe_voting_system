from flask import Flask, request, jsonify, send_from_directory, session
import os
from datetime import datetime, timedelta
import pytz
from psycopg2 import pool

app = Flask(__name__)
app.secret_key = "supersecretkey"  # palitan mo ito ng mas secure na string

PH_TZ = pytz.timezone("Asia/Manila")

# --- Simple in-memory cache for scoreboard ---
scoreboard_cache = {"data": None, "timestamp": 0}

# --- Connection Pool Setup ---
DATABASE_URL = os.environ.get("DATABASE_URL")
db_pool = pool.SimpleConnectionPool(1, 10, DATABASE_URL)

def get_db_connection():
    return db_pool.getconn()

def release_db_connection(conn):
    db_pool.putconn(conn)

# --- Initialize DB with candidates ---
def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
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
                id SERIAL PRIMARY KEY,
                ticket_id TEXT,
                student_name TEXT,
                candidate_id TEXT,
                gender TEXT,
                timestamp TIMESTAMP,
                is_valid BOOLEAN DEFAULT TRUE
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
            INSERT INTO candidates (id, name, org, program, gender, image, votes)
            VALUES (%s, %s, %s, %s, %s, %s, 0)
            ON CONFLICT (id) DO NOTHING
        """, cand)

        conn.commit()
    finally:
        cursor.close()
        release_db_connection(conn)

init_db()

# --- Helper function to get results (admin full view) ---
def get_results():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # FIX: declare alias AS v para gumana ang v.is_valid
        cursor.execute("""
            SELECT c.gender, COUNT(*) 
            FROM votes AS v
            JOIN candidates AS c ON v.candidate_id = c.id
            WHERE v.is_valid = TRUE
            GROUP BY c.gender
        """)
        total_valid_votes = dict(cursor.fetchall())

        cursor.execute("""
            SELECT c.gender, COALESCE(SUM(f.reactions),0)
            FROM candidates AS c
            LEFT JOIN fb_reactions AS f ON c.id = f.candidate_id
            GROUP BY c.gender
        """)
        total_fb_reacts = dict(cursor.fetchall())

        cursor.execute("""
            SELECT c.id, c.name, c.org, c.program, c.gender, c.image,
                   c.votes AS system_votes,
                   COALESCE(f.reactions, 0) AS fb_reactions
            FROM candidates AS c
            LEFT JOIN fb_reactions AS f ON c.id = f.candidate_id
        """)
        rows = cursor.fetchall()
    finally:
        cursor.close()
        release_db_connection(conn)

    results = []
    for row in rows:
        cid, name, org, program, gender, image, sys_votes, fb_reacts = row
        sys_total = total_valid_votes.get(gender, 0)
        fb_total = total_fb_reacts.get(gender, 0)
        sys_percent = (sys_votes / sys_total * 100) if sys_total > 0 else 0
        fb_percent = (fb_reacts / fb_total * 100) if fb_total > 0 else 0
        darling_score = round((sys_percent/100 * 50) + (fb_percent/100 * 50), 2)

        results.append({
            "id": cid,
            "name": name,
            "org": org,
            "program": program,
            "gender": gender,
            "image": image,
            "system_votes": sys_votes,
            "fb_reactions": fb_reacts,
            "darling_score": darling_score,
            "system_percent": round(sys_percent,2),
            "fb_percent": round(fb_percent,2)
        })
    return results

# --- Voting endpoint ---
@app.route("/vote", methods=["POST"])
def vote():
    data = request.get_json()
    ticket_id = data.get("ticket_id")
    student_name = data.get("student_name")
    votes = data.get("votes", [])

    if student_name and student_name.startswith("A") and "-" in student_name:
        return jsonify({"message": "Please enter your full name, not your student ID."}), 400

    now = datetime.now(PH_TZ)
    start = PH_TZ.localize(datetime(2026, 3, 23, 11, 0, 0))
    end = PH_TZ.localize(datetime(2026, 3, 30, 12, 0, 0))

    if now < start or now > end:
        return jsonify({"message": "Voting is closed. Valid period is March 23–30, Philippine Time."}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        errors = []
        for v in votes:
            candidate_id = v.get("candidate_id")
            gender = v.get("gender")
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            today_end = today_start + timedelta(days=1, seconds=-1)
            cursor.execute("""
                SELECT COUNT(*) FROM votes
                WHERE ticket_id=%s AND gender=%s AND timestamp BETWEEN %s AND %s AND is_valid=TRUE
            """, (ticket_id, gender, today_start, today_end))
            already_voted = cursor.fetchone()[0]
            if already_voted > 0:
                errors.append(gender)

        if errors:
            return jsonify({"message": f"You have already voted today for {', '.join(errors)} category."}), 400

        for v in votes:
            candidate_id = v.get("candidate_id")
            gender = v.get("gender")
            cursor.execute("""
                INSERT INTO votes (ticket_id, student_name, candidate_id, gender, timestamp, is_valid)
                VALUES (%s, %s, %s, %s, %s, TRUE)
            """, (ticket_id, student_name, candidate_id, gender, now))
            cursor.execute("UPDATE candidates SET votes = votes + 1 WHERE id=%s", (candidate_id,))

        conn.commit()
    finally:
        cursor.close()
        release_db_connection(conn)

    scoreboard_cache["data"] = None
    scoreboard_cache["timestamp"] = 0
    return jsonify({"message": "Votes recorded successfully."}), 200

# --- Results endpoint ---
@app.route("/results", methods=["GET"])
def results():
    try:
        candidates_data = get_results()

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT id, ticket_id, student_name, candidate_id, gender, timestamp, is_valid
                FROM votes
                ORDER BY timestamp DESC
            """)
            votes_rows = cursor.fetchall()
        finally:
            cursor.close()
            release_db_connection(conn)

        votes_data = []
        for row in votes_rows:
            votes_data.append({
                "id": row[0],
                "ticket_id": row[1],
                "student_name": row[2],
                "candidate_id": row[3],
                "gender": row[4],
                "timestamp": row[5].isoformat() if row[5] else None,
                "is_valid": row[6]
            })

        return jsonify({
            "candidates": candidates_data,
            "votes": votes_data
        }), 200

    except Exception as e:
        print("Error in /results:", e)
        return jsonify({"message": "Error loading results"}), 500

# --- Update FB reactions endpoint (protected) ---
@app.route("/update_fb", methods=["POST"])
def update_fb():
    if not session.get("admin_logged_in"):
        return jsonify({"message": "Unauthorized"}), 403

    data = request.get_json()
    candidate_id = str(data.get("candidate_id"))
    reactions = int(data.get("reactions"))

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO fb_reactions (candidate_id, reactions)
            VALUES (%s, %s)
            ON CONFLICT (candidate_id) DO UPDATE SET reactions = EXCLUDED.reactions
        """, (candidate_id, reactions))
        conn.commit()
    finally:
        cursor.close()
        release_db_connection(conn)

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