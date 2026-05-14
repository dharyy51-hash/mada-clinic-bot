from flask import Flask, request, jsonify, render_template, session
from bot import get_bot_response
from configs import get_config, BUSINESS_CONFIGS
from dotenv import load_dotenv
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from datetime import datetime
import os, uuid, sqlite3

load_dotenv()

BOOKING_KEYWORDS = ["تم تسجيل طلب موعدك", "تم تسجيل طلبك", "سيتواصل معك", "سنتواصل معك", "تم تحديث موعدك"]
MAX_MSG_LENGTH = 500

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "mada-kw-secret-2024")

limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://"
)

conversations = {}


# ── Database ──────────────────────────────────────────────
def get_db():
    db = sqlite3.connect("bookings.db", check_same_thread=False)
    db.execute("""CREATE TABLE IF NOT EXISTS bookings (
        id       INTEGER PRIMARY KEY AUTOINCREMENT,
        time     TEXT,
        business TEXT,
        chat     TEXT
    )""")
    db.commit()
    return db


def save_booking(conversation, business_type):
    recent = conversation[-8:] if len(conversation) > 8 else conversation
    lines = []
    for msg in recent:
        role = "العميل" if msg["role"] == "user" else "البوت"
        lines.append(f"{role}: {msg['content']}")
    try:
        db = get_db()
        db.execute(
            "INSERT INTO bookings (time, business, chat) VALUES (?, ?, ?)",
            (datetime.now().strftime("%Y-%m-%d %H:%M"), business_type, "\n".join(lines))
        )
        db.commit()
        db.close()
    except Exception as e:
        print(f"DB ERROR: {e}")


# ── Routes ────────────────────────────────────────────────
@app.route("/")
@app.route("/<business_type>")
def index(business_type="clinic"):
    if business_type not in BUSINESS_CONFIGS:
        business_type = "clinic"
    session["session_id"]    = str(uuid.uuid4())
    session["business_type"] = business_type
    config = get_config(business_type)
    return render_template("index.html", clinic=config, config=config, business_type=business_type)


@app.route("/chat", methods=["POST"])
@limiter.limit("20 per hour")
def chat():
    data          = request.json
    user_message  = data.get("message", "").strip()
    session_id    = session.get("session_id", str(uuid.uuid4()))
    business_type = session.get("business_type", "clinic")

    if not user_message:
        return jsonify({"error": "رسالة فارغة"}), 400

    if len(user_message) > MAX_MSG_LENGTH:
        return jsonify({"reply": "رسالتك طويلة جداً، اختصرها من فضلك."}), 200

    if session_id not in conversations:
        conversations[session_id] = []

    conversations[session_id].append({"role": "user", "content": user_message})

    try:
        reply = get_bot_response(conversations[session_id], business_type)
    except Exception as e:
        return jsonify({"reply": f"خطأ في الاتصال: {str(e)}"}), 200

    conversations[session_id].append({"role": "assistant", "content": reply})

    if any(kw in reply for kw in BOOKING_KEYWORDS):
        save_booking(conversations[session_id], business_type)

    if len(conversations[session_id]) > 20:
        conversations[session_id] = conversations[session_id][-20:]

    return jsonify({"reply": reply})


@app.route("/bookings")
def show_bookings():
    key          = request.args.get("key", "")
    bookings_key = os.environ.get("BOOKINGS_KEY", os.environ.get("SECRET_KEY", "mada2024"))
    if key != bookings_key:
        return "<h3 style='font-family:Arial;padding:20px'>غير مصرح ❌</h3>", 403

    business_filter = request.args.get("b", "")

    try:
        db   = get_db()
        if business_filter:
            rows = db.execute(
                "SELECT time, business, chat FROM bookings WHERE business=? ORDER BY id DESC",
                (business_filter,)
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT time, business, chat FROM bookings ORDER BY id DESC"
            ).fetchall()
        db.close()
    except Exception:
        rows = []

    if not rows:
        return "<h2 style='font-family:Arial;direction:rtl;padding:20px'>لا توجد حجوزات بعد</h2>"

    html  = "<html><head><meta charset='utf-8'><style>"
    html += "body{font-family:Arial;direction:rtl;padding:20px;background:#F7F7F8;color:#0D0D0D}"
    html += "h2{margin-bottom:20px}.card{background:#fff;margin:12px 0;padding:16px;border-radius:12px;"
    html += "border-right:4px solid #19C37D;box-shadow:0 2px 8px rgba(0,0,0,0.06)}"
    html += ".meta{font-weight:700;margin-bottom:8px;color:#19C37D}"
    html += "pre{white-space:pre-wrap;color:#444;font-size:13px;line-height:1.7}"
    html += "</style></head><body>"
    html += f"<h2>📅 الحجوزات ({len(rows)})</h2>"
    for time, business, chat in rows:
        html += f"<div class='card'><div class='meta'>🕐 {time} &nbsp;|&nbsp; {business}</div>"
        html += f"<pre>{chat}</pre></div>"
    html += "</body></html>"
    return html


@app.route("/reset", methods=["POST"])
def reset():
    session_id = session.get("session_id")
    if session_id in conversations:
        del conversations[session_id]
    return jsonify({"status": "ok"})


@app.route("/webhook/whatsapp/<business_type>", methods=["POST"])
def whatsapp_webhook(business_type="clinic"):
    from_number = request.form.get("From", "")
    body        = request.form.get("Body", "").strip()

    if not body:
        return "", 200

    key = f"{business_type}:{from_number}"
    if key not in conversations:
        conversations[key] = []

    conversations[key].append({"role": "user", "content": body})
    reply = get_bot_response(conversations[key], business_type)
    conversations[key].append({"role": "assistant", "content": reply})

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response><Message>{reply}</Message></Response>"""
    return twiml, 200, {"Content-Type": "text/xml"}


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
