"""
MomoStrap Chatbot Backend — Render-ready (Google Gemini)
=========================================================
- Serves index.html from Flask itself
- Uses Google Gemini API (gemini-2.0-flash) for AI responses
- Uses PostgreSQL when DATABASE_URL is set, else SQLite locally
- All secrets via environment variables
"""

import os
import sqlite3                    # always imported — used as local fallback
from datetime import datetime
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from google import genai
from google.genai import types

# PostgreSQL is optional
try:
    import psycopg2
except ImportError:
    psycopg2 = None

# ── App setup ──────────────────────────────────────────────────────────────────
app = Flask(__name__)
CORS(app)

GEMINI_MODEL = "gemini-2.0-flash"

# Use PostgreSQL if DATABASE_URL is set, else SQLite
DATABASE_URL = os.environ.get("DATABASE_URL", "")
USE_POSTGRES  = bool(psycopg2 and DATABASE_URL)
SQLITE_PATH   = "chat_history.db"

# Gemini client is created lazily (at first request) so the app starts
# cleanly even before GOOGLE_API_KEY is confirmed valid.
_gemini_client = None

def get_gemini():
    """Return a cached Gemini client, creating it on first call."""
    global _gemini_client
    if _gemini_client is None:
        api_key = os.environ.get("GOOGLE_API_KEY", "")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY environment variable is not set")
        _gemini_client = genai.Client(api_key=api_key)
    return _gemini_client


# ── System prompt ──────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are MomoBot, the friendly customer support assistant for MomoStrap
— a modern lifestyle brand selling premium backpack straps and bag accessories.

Your personality: warm, helpful, slightly playful, uses occasional emojis, always solution-oriented.

PRODUCTS:
- ClassicStrap Pro    Rs.1,499  Adjustable padded strap, bags up to 15 kg
- UltraComfort X      Rs.2,299  Ergonomic anti-fatigue strap with memory foam
- SportFlex Elite     Rs.1,899  Sweat-resistant, great for gym/outdoor
- MiniStrap Duo       Rs.999    Compact dual-clip strap for small bags
- CityCarry Bundle    Rs.3,499  2 straps + organizer pouch kit

FAQs:
- Shipping: 3-5 days standard; express 1-2 days (Rs.99 extra); free above Rs.999
- Returns: 30-day hassle-free returns to support@momostrap.in
- Warranty: 1 year manufacturing defects
- Payment: UPI, cards, net banking, EMI above Rs.2,000
- Strap sizes: 80 cm to 145 cm adjustable

For complaints: acknowledge empathetically first, then resolve step by step.
Keep responses under 120 words unless listing products. Always end with a follow-up offer.
"""

# ── Database helpers ───────────────────────────────────────────────────────────

def get_conn():
    """Return a DB connection — PostgreSQL if available, else SQLite."""
    if USE_POSTGRES:
        url = DATABASE_URL.replace("postgres://", "postgresql://", 1)
        return psycopg2.connect(url)
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables on first start."""
    conn = get_conn()
    cur  = conn.cursor()
    if USE_POSTGRES:
        cur.execute("""CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY, created TEXT NOT NULL)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS messages (
            id SERIAL PRIMARY KEY, session_id TEXT NOT NULL,
            role TEXT NOT NULL, content TEXT NOT NULL, ts TEXT NOT NULL)""")
    else:
        cur.execute("""CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY, created TEXT NOT NULL)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL,
            role TEXT NOT NULL, content TEXT NOT NULL, ts TEXT NOT NULL)""")
    conn.commit()
    cur.close()
    conn.close()


def save_message(session_id, role, content):
    """Save one message to the database."""
    conn = get_conn()
    cur  = conn.cursor()
    now  = datetime.utcnow().isoformat()
    if USE_POSTGRES:
        cur.execute("INSERT INTO sessions (id,created) VALUES (%s,%s) ON CONFLICT DO NOTHING",
                    (session_id, now))
        cur.execute("INSERT INTO messages (session_id,role,content,ts) VALUES (%s,%s,%s,%s)",
                    (session_id, role, content, now))
    else:
        cur.execute("INSERT OR IGNORE INTO sessions (id,created) VALUES (?,?)",
                    (session_id, now))
        cur.execute("INSERT INTO messages (session_id,role,content,ts) VALUES (?,?,?,?)",
                    (session_id, role, content, now))
    conn.commit()
    cur.close()
    conn.close()


def get_history(session_id, limit=20):
    """Return last N messages for a session, oldest first."""
    conn = get_conn()
    cur  = conn.cursor()
    if USE_POSTGRES:
        cur.execute(
            "SELECT role,content FROM messages WHERE session_id=%s ORDER BY id DESC LIMIT %s",
            (session_id, limit))
        rows = [{"role": r[0], "content": r[1]} for r in cur.fetchall()]
    else:
        cur.execute(
            "SELECT role,content FROM messages WHERE session_id=? ORDER BY id DESC LIMIT ?",
            (session_id, limit))
        rows = [{"role": r["role"], "content": r["content"]} for r in cur.fetchall()]
    cur.close()
    conn.close()
    return list(reversed(rows))


def build_gemini_contents(history, user_message):
    """
    Build Gemini Content list from DB history + new user message.
    Gemini uses 'user' and 'model' roles (not 'assistant').
    """
    contents = []
    for msg in history:
        if msg["role"] == "user":
            contents.append(types.UserContent(parts=[msg["content"]]))
        else:
            # 'assistant' stored in DB → 'model' for Gemini
            contents.append(types.ModelContent(parts=[msg["content"]]))
    # Append the new user message
    contents.append(types.UserContent(parts=[user_message]))
    return contents


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    """Serve the chat UI."""
    return send_file("index.html")


@app.route("/health")
def health():
    return jsonify({"status": "ok", "bot": "MomoBot", "ai": "gemini-2.0-flash",
                    "db": "postgres" if USE_POSTGRES else "sqlite"})


@app.route("/chat", methods=["POST"])
def chat():
    """
    POST /chat
    Body:    { "session_id": "abc", "message": "What straps do you sell?" }
    Returns: { "reply": "...", "session_id": "...", "timestamp": "..." }
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be JSON"}), 400

    session_id   = data.get("session_id", "").strip()
    user_message = data.get("message",    "").strip()

    if not session_id:   return jsonify({"error": "session_id required"}), 400
    if not user_message: return jsonify({"error": "message required"}),    400

    # Load history and save new user message
    history = get_history(session_id)
    save_message(session_id, "user", user_message)

    # Build Gemini content list (history + current message)
    contents = build_gemini_contents(history, user_message)

    # Call Gemini
    try:
        client   = get_gemini()
        response = client.models.generate_content(
            model    = GEMINI_MODEL,
            contents = contents,
            config   = types.GenerateContentConfig(
                system_instruction = SYSTEM_PROMPT,
                max_output_tokens  = 1024,
                temperature        = 0.7,
            )
        )
        bot_reply = response.text
    except ValueError as e:
        return jsonify({"error": str(e)}), 401
    except Exception as e:
        err = str(e)
        if "API_KEY" in err.upper() or "401" in err or "403" in err:
            return jsonify({"error": "Invalid API key — check GOOGLE_API_KEY env var"}), 401
        if "429" in err or "quota" in err.lower():
            return jsonify({"error": "Rate limit hit, please slow down"}), 429
        return jsonify({"error": err}), 500

    save_message(session_id, "assistant", bot_reply)
    return jsonify({"reply": bot_reply, "session_id": session_id,
                    "timestamp": datetime.utcnow().isoformat()})


@app.route("/history/<session_id>")
def history(session_id):
    return jsonify({"session_id": session_id,
                    "messages": get_history(session_id, 200)})


@app.route("/sessions")
def sessions():
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT id,created FROM sessions ORDER BY created DESC")
    rows = cur.fetchall(); cur.close(); conn.close()
    if USE_POSTGRES:
        return jsonify({"sessions": [{"id": r[0], "created": r[1]} for r in rows]})
    return jsonify({"sessions": [dict(r) for r in rows]})


@app.route("/faqs")
def faqs():
    return jsonify({"faqs": [
        {"q": "How long does shipping take?",
         "a": "Standard 3-5 days. Express 1-2 days (Rs.99). Free above Rs.999."},
        {"q": "What is the return policy?",
         "a": "30-day hassle-free returns. Email support@momostrap.in."},
        {"q": "Do straps come with a warranty?",
         "a": "Yes, 1 year against manufacturing defects."},
        {"q": "What payment methods are accepted?",
         "a": "UPI, cards, net banking, EMI on orders above Rs.2,000."},
        {"q": "What sizes are available?",
         "a": "All straps adjust from 80 cm to 145 cm."},
    ]})


# ── Init DB on every gunicorn worker start ─────────────────────────────────────
init_db()

if __name__ == "__main__":
    print("MomoBot (Gemini) running at http://localhost:5000")
    app.run(debug=True, port=5000)
