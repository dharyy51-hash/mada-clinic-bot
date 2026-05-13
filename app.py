from flask import Flask, request, jsonify, render_template, session
from bot import get_bot_response
from configs import get_config, BUSINESS_CONFIGS
from dotenv import load_dotenv
import os, uuid
from datetime import datetime

load_dotenv()

BOOKING_KEYWORDS = ["تم تسجيل طلب موعدك", "تم تسجيل طلبك", "سيتواصل معك", "سنتواصل معك", "تم تحديث موعدك"]

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "mada-kw-secret-2024")

conversations = {}
bookings = []


def save_booking(conversation, business_type):
    recent = conversation[-8:] if len(conversation) > 8 else conversation
    lines = []
    for msg in recent:
        role = "العميل" if msg["role"] == "user" else "البوت"
        lines.append(f"{role}: {msg['content']}")
    bookings.append({
        "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "business": business_type,
        "chat": "\n".join(lines)
    })


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
def chat():
    data          = request.json
    user_message  = data.get("message", "").strip()
    session_id    = session.get("session_id", str(uuid.uuid4()))
    business_type = session.get("business_type", "clinic")

    if not user_message:
        return jsonify({"error": "رسالة فارغة"}), 400

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
    password = request.args.get("key", "")
    if password != os.environ.get("SECRET_KEY", "mada2024"):
        return "غير مصرح", 403
    if not bookings:
        return "<h2 style='font-family:Arial;direction:rtl;padding:20px'>لا توجد حجوزات بعد</h2>"
    html = "<html><head><meta charset='utf-8'></head><body style='font-family:Arial;direction:rtl;padding:20px;background:#0D1B2A;color:white'>"
    html += f"<h2>📅 الحجوزات ({len(bookings)})</h2>"
    for b in reversed(bookings):
        html += f"<div style='background:#1a2d42;margin:10px 0;padding:15px;border-radius:8px;border-right:4px solid #00D4FF'>"
        html += f"<b>🕐 {b['time']} | {b['business']}</b><pre style='white-space:pre-wrap;color:#ccc'>{b['chat']}</pre></div>"
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
