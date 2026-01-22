import os
import pyodbc
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)

# Allow ONLY your static website to call /api/*
CORS(app, resources={r"/api/*": {"origins": ["https://ataurweb2026.z29.web.core.windows.net"]}})

def get_conn():
    server = os.environ["DB_SERVER"]
    db = os.environ["DB_NAME"]
    user = os.environ["DB_USER"]
    password = os.environ["DB_PASSWORD"]

    conn_str = (
        "DRIVER={ODBC Driver 18 for SQL Server};"
        f"SERVER={server};"
        f"DATABASE={db};"
        f"UID={user};"
        f"PWD={password};"
        "Encrypt=yes;"
        "TrustServerCertificate=no;"
        "Connection Timeout=30;"
    )
    return pyodbc.connect(conn_str)

@app.get("/")
def health():
    return "Backend running OK"

@app.get("/api/messages")
def get_messages():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT TOP 20 Username, MessageText, CreatedAt
            FROM dbo.Messages
            ORDER BY CreatedAt DESC
        """)
        rows = cur.fetchall()

    return jsonify([
        {"username": r[0], "text": r[1], "createdAt": r[2].isoformat()}
        for r in rows
    ])

@app.post("/api/messages")
def post_message():
    payload = request.get_json(force=True) or {}
    username = (payload.get("username") or "").strip()
    text = (payload.get("text") or "").strip()

    if not username or not text:
        return jsonify({"error": "username and text are required"}), 400

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO dbo.Messages (Username, MessageText) VALUES (?, ?)",
            (username, text)
        )
        conn.commit()

    return jsonify({"ok": True}), 201
