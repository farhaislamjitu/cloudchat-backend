import os
import tds
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Enable CORS for frontend access


def get_conn():
    try:
        return tds.connect(
            server=os.environ["DB_SERVER"],
            database=os.environ["DB_NAME"],
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"],
            port=1433,
            autocommit=True,
            tds_version=tds.TDS74
        )
    except Exception as e:
        print(f"Database connection error: {e}")
        raise


@app.get("/")
def health():
    return "Backend running OK"


@app.get("/api/messages")
def get_messages():
    try:
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
            {
                "username": r[0],
                "text": r[1],
                "createdAt": str(r[2])
            }
            for r in rows
        ]

        return jsonify(list(reversed(data)))

    except Exception as e:
        print(f"Error fetching messages: {e}")
        return jsonify({"error": str(e)}), 500


@app.post("/api/messages")
def add_message():
    try:
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

    except Exception as e:
        print(f"Error saving message: {e}")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=False)
