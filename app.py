import os
import pyodbc
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)


# Database connection
def get_conn():
    server = os.environ.get("DB_SERVER")
    database = os.environ.get("DB_NAME")
    username = os.environ.get("DB_USER")
    password = os.environ.get("DB_PASSWORD")

    conn_str = (
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={server};"
        f"DATABASE={database};"
        f"UID={username};"
        f"PWD={password};"
        "Encrypt=yes;"
        "TrustServerCertificate=no;"
        "Connection Timeout=30;"
    )
    return pyodbc.connect(conn_str)


# Helper: get or create private conversation
def get_or_create_private_conversation(cur, user1_id, user2_id):
    cur.execute(
        """
        SELECT pcm1.conversation_id
        FROM dbo.private_conversation_members pcm1
        INNER JOIN dbo.private_conversation_members pcm2
            ON pcm1.conversation_id = pcm2.conversation_id
        WHERE pcm1.user_id = ? AND pcm2.user_id = ?
        """,
        (user1_id, user2_id),
    )
    row = cur.fetchone()

    if row:
        return row[0]

    cur.execute("INSERT INTO dbo.private_conversations DEFAULT VALUES;")
    cur.execute("SELECT CAST(SCOPE_IDENTITY() AS INT);")
    conversation_id = cur.fetchone()[0]

    cur.execute(
        "INSERT INTO dbo.private_conversation_members (conversation_id, user_id) VALUES (?, ?)",
        (conversation_id, user1_id),
    )
    cur.execute(
        "INSERT INTO dbo.private_conversation_members (conversation_id, user_id) VALUES (?, ?)",
        (conversation_id, user2_id),
    )

    return conversation_id


# Health check (for Load Balancer)
@app.get("/")
def health():
    return "Backend running OK"


# =========================
# GROUP CHAT ROUTES
# =========================

# Get messages
@app.get("/api/messages")
def get_messages():
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT TOP 20 Username, MessageText, CreatedAt
                FROM dbo.Messages
                ORDER BY CreatedAt DESC
                """
            )
            rows = cur.fetchall()

        return jsonify(
            [
                {
                    "username": r[0],
                    "text": r[1],
                    "createdAt": r[2].isoformat() if r[2] else None,
                }
                for r in rows
            ]
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# Post message
@app.post("/api/messages")
def post_message():
    try:
        payload = request.get_json(force=True) or {}
        username = (payload.get("username") or "").strip()
        text = (payload.get("text") or "").strip()

        if not username or not text:
            return jsonify({"error": "username and text are required"}), 400

        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO dbo.Messages (Username, MessageText) VALUES (?, ?)",
                (username, text),
            )
            conn.commit()

        return jsonify({"ok": True}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =========================
# PRIVATE CHAT ROUTES
# =========================

# Create or get private user
@app.post("/api/private-users")
def create_private_user():
    try:
        payload = request.get_json(force=True) or {}
        username = (payload.get("username") or "").strip()

        if not username:
            return jsonify({"error": "username is required"}), 400

        with get_conn() as conn:
            cur = conn.cursor()

            cur.execute(
                "SELECT id, username FROM dbo.private_users WHERE username = ?",
                (username,),
            )
            row = cur.fetchone()

            if row:
                return jsonify(
                    {
                        "id": row[0],
                        "username": row[1],
                        "message": "user already exists",
                    }
                ), 200

            cur.execute(
                "INSERT INTO dbo.private_users (username) OUTPUT INSERTED.id VALUES (?)",
                (username,),
            )
            user_id = cur.fetchone()[0]
            conn.commit()

        return jsonify(
            {
                "id": user_id,
                "username": username,
                "message": "user created",
            }
        ), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# Send private message
@app.post("/api/private-chat/send")
def send_private_message():
    try:
        payload = request.get_json(force=True) or {}
        sender = (payload.get("sender") or "").strip()
        recipient = (payload.get("recipient") or "").strip()
        message = (payload.get("message") or "").strip()

        if not sender or not recipient or not message:
            return jsonify({"error": "sender, recipient and message are required"}), 400

        if sender == recipient:
            return jsonify({"error": "sender and recipient cannot be the same"}), 400

        with get_conn() as conn:
            cur = conn.cursor()

            cur.execute(
                "SELECT id FROM dbo.private_users WHERE username = ?",
                (sender,),
            )
            sender_row = cur.fetchone()

            cur.execute(
                "SELECT id FROM dbo.private_users WHERE username = ?",
                (recipient,),
            )
            recipient_row = cur.fetchone()

            if not sender_row:
                return jsonify({"error": f"sender '{sender}' not found"}), 404

            if not recipient_row:
                return jsonify({"error": f"recipient '{recipient}' not found"}), 404

            sender_id = sender_row[0]
            recipient_id = recipient_row[0]

            conversation_id = get_or_create_private_conversation(
                cur, sender_id, recipient_id
            )

            cur.execute(
                """
                INSERT INTO dbo.private_messages (conversation_id, sender_id, message)
                OUTPUT INSERTED.id, INSERTED.created_at
                VALUES (?, ?, ?)
                """,
                (conversation_id, sender_id, message),
            )
            inserted = cur.fetchone()
            conn.commit()

        return jsonify(
            {
                "message_id": inserted[0],
                "conversation_id": conversation_id,
                "sender": sender,
                "recipient": recipient,
                "message": message,
                "created_at": inserted[1].isoformat() if inserted[1] else None,
            }
        ), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# Get private chat history
@app.get("/api/private-chat/history")
def get_private_chat_history():
    try:
        user1 = (request.args.get("user1") or "").strip()
        user2 = (request.args.get("user2") or "").strip()

        if not user1 or not user2:
            return jsonify({"error": "user1 and user2 are required"}), 400

        with get_conn() as conn:
            cur = conn.cursor()

            cur.execute(
                "SELECT id FROM dbo.private_users WHERE username = ?",
                (user1,),
            )
            row1 = cur.fetchone()

            cur.execute(
                "SELECT id FROM dbo.private_users WHERE username = ?",
                (user2,),
            )
            row2 = cur.fetchone()

            if not row1 or not row2:
                return jsonify({"messages": []}), 200

            user1_id = row1[0]
            user2_id = row2[0]

            cur.execute(
                """
                SELECT pcm1.conversation_id
                FROM dbo.private_conversation_members pcm1
                INNER JOIN dbo.private_conversation_members pcm2
                    ON pcm1.conversation_id = pcm2.conversation_id
                WHERE pcm1.user_id = ? AND pcm2.user_id = ?
                """,
                (user1_id, user2_id),
            )
            conv = cur.fetchone()

            if not conv:
                return jsonify({"messages": []}), 200

            conversation_id = conv[0]

            cur.execute(
                """
                SELECT
                    pm.id,
                    pu.username AS sender,
                    pm.message,
                    pm.created_at
                FROM dbo.private_messages pm
                INNER JOIN dbo.private_users pu
                    ON pm.sender_id = pu.id
                WHERE pm.conversation_id = ?
                ORDER BY pm.created_at ASC
                """,
                (conversation_id,),
            )
            rows = cur.fetchall()

        return jsonify(
            {
                "conversation_id": conversation_id,
                "messages": [
                    {
                        "id": r[0],
                        "sender": r[1],
                        "message": r[2],
                        "created_at": r[3].isoformat() if r[3] else None,
                    }
                    for r in rows
                ],
            }
        ), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# Run app
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
