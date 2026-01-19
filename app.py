import os
from flask import Flask, request, jsonify
import pytds

app = Flask(__name__)

def get_conn():
    return pytds.connect(
        server=os.environ["DB_SERVER"],
        database=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        port=1433,
        autocommit=True,
        tds_version=pytds.TDS74
    )

@app.get("/")
def health():
    return "Backend running OK"

@app.get("/api/messages")
def get_messages():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT TOP 20 Username, MessageText, CreatedAt
        FROM Messages
        ORDER BY CreatedAt DESC
    """)
    rows = cur.fetchall()
    conn.close()

    data = [
        {"username": r[0], "text": r[1], "createdAt": str(r[2])}
        for r in rows
    ]
    return jsonify(list(reversed(data)))

@app.post("/api/messages")
def add_message():
    body = request.get_json(force=True)
    username = body.get("username", "").strip()
    text = body.get("text", "").strip()

    if not username or not text:
        return jsonify({"error": "username and text are required"}), 400

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO Messages (Username, MessageText) VALUES (?, ?)",
        (username, text)
    )
    conn.commit()
    conn.close()

    return jsonify({"status": "saved"}), 201
